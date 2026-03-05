import asyncio
import aiohttp
import pyzipper
import os
import re
import time

ZIP_PASS = os.getenv('ZIP_PASSWORD')
MAX_CONCURRENT = 150 # Ekshathe 150-ti link check korbe speed baranor jonno

async def check_and_get_latency(semaphore, session, url, headers):
    """Link-ti open ache ki na ebong koto fast seta check korbe"""
    async with semaphore:
        try:
            start_time = time.time()
            # Timeout matro 2 second rakha hoyeche jate slow link bad pore jay
            async with session.get(url, headers=headers, timeout=2) as response:
                if response.status == 200:
                    return time.time() - start_time
        except:
            pass
        return float('inf')

async def main():
    def read_file(filename):
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        return []

    blocked = read_file('block_link.txt')
    target_data = read_file('targets.txt')
    
    # targets.txt theke serial ebong logo load kora
    ordered_targets = []
    for line in target_data:
        if ',' in line:
            name, logo = line.split(',', 1)
            ordered_targets.append({"name": name.strip(), "logo": logo.strip()})

    # tera.zip file theke sources load kora
    try:
        with pyzipper.AESZipFile('tera.zip') as zf:
            zf.setpassword(ZIP_PASS.encode('utf-8'))
            sources = [line.decode('utf-8').strip() for line in zf.open('sources.txt') if line.strip()]
    except Exception as e:
        print(f"Zip error: {e}")
        return

    # Shob source theke link pool-e joma kora
    pool = {} # {channel_name_lower: [links]}
    async with aiohttp.ClientSession() as session:
        for s_url in sources:
            try:
                async with session.get(s_url, timeout=5) as r:
                    content = await r.text()
                    chunks = re.split(r'#EXTINF', content)
                    for chunk in chunks[1:]:
                        lines = chunk.strip().split('\n')
                        name_match = re.search(r',(.+)$', lines[0])
                        if not name_match: continue
                        raw_name = name_match.group(1).strip().lower()

                        url, meta = "", {"props": [], "ua": "Mozilla/5.0"}
                        for l in lines[1:]:
                            if l.startswith('http'): url = l.strip()
                            elif l.startswith('#'):
                                meta['props'].append(l.strip())
                                if 'User-Agent=' in l: meta['ua'] = l.split('=')[1]

                        if url and not any(b in url for b in blocked):
                            # targets.txt-er namer sathe match kora
                            for t in ordered_targets:
                                if t['name'].lower() in raw_name:
                                    pool.setdefault(t['name'].lower(), []).append({"url": url, "meta": meta})
                                    break
            except: continue

        # Speed check ebong best link selection
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        final_playlist = []

        for target in ordered_targets:
            t_key = target['name'].lower()
            if t_key in pool:
                links = pool[t_key]
                tasks = [check_and_get_latency(semaphore, session, l['url'], {'User-Agent': l['meta']['ua']}) for l in links]
                latencies = await asyncio.gather(*tasks)
                
                # Sobtheke kom latency-r (buffer-less) link-ti neya hobe
                best_idx = -1
                min_lat = float('inf')
                for i, lat in enumerate(latencies):
                    if lat < min_lat:
                        min_lat = lat
                        best_idx = i
                
                if best_idx != -1:
                    best = links[best_idx]
                    entry = f'#EXTINF:-1 tvg-logo="{target["logo"]}", {target["name"]}\n'
                    if best['meta']['props']:
                        entry += "\n".join(best['meta']['props']) + "\n"
                    entry += f"{best['url']}"
                    final_playlist.append(entry)

        # playlist.m3u write kora
        with open("playlist.m3u", "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n" + "\n".join(final_playlist))

if __name__ == "__main__":
    asyncio.run(main())
