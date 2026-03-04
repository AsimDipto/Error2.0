import asyncio
import aiohttp
import pyzipper
import os
import re
import time

# গিটহাব সিক্রেট থেকে পাসওয়ার্ড নিবে
ZIP_PASS = os.getenv('ZIP_PASSWORD')
MAX_CONCURRENT = 500 

async def get_latency(semaphore, session, url, headers):
    """সবচেয়ে দ্রুত (Buffer-less) লিঙ্ক বাছাই করার জন্য ল্যাটেন্সি চেক করে"""
    async with semaphore:
        start_time = time.time()
        try:
            async with session.get(url, headers=headers, timeout=5) as response:
                if response.status == 200:
                    return time.time() - start_time
        except:
            pass
        return float('inf')

async def main():
    def read_repo_file(filename):
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        return []

    # রিপোজিটরির মেইন ফোল্ডার থেকে ফাইল পড়া (Zip এর বাইরে)
    blocked_keywords = read_repo_file('block_link.txt')
    targets = read_repo_file('targets.txt')
    
    target_map = {}
    for t in targets:
        if ',' in t:
            name, logo = t.split(',', 1)
            target_map[name.strip().lower()] = {"raw_name": name.strip(), "logo": logo.strip()}

    # জিপ ফাইলের নাম 'tera.zip' সাপোর্ট করবে
    zip_path = 'tera.zip'
    if not os.path.exists(zip_path):
        if os.path.exists('links.zip'): zip_path = 'links.zip'
        else:
            print("Error: Zip file not found!")
            return

    try:
        with pyzipper.AESZipFile(zip_path) as zf:
            zf.setpassword(ZIP_PASS.encode('utf-8'))
            with zf.open('sources.txt') as f:
                sources = [line.decode('utf-8').strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Zip Error: {e}")
        return

    candidate_links = {} 
    
    async with aiohttp.ClientSession() as session:
        for m3u_url in sources:
            try:
                async with session.get(m3u_url, timeout=10) as response:
                    content = await response.text()
                    # DRM (Clearkey/Kodi), User-Agent, Cookie সহ সব মেটাডেটা প্রসেস করবে
                    chunks = re.split(r'#EXTINF', content)
                    for chunk in chunks[1:]:
                        lines = chunk.strip().split('\n')
                        name_match = re.search(r',(.+)$', lines[0])
                        if not name_match: continue
                        
                        raw_name = name_match.group(1).strip()
                        clean_name = raw_name.lower()

                        # টার্গেট লিস্টে থাকা চ্যানেলগুলো ম্যাচ করা
                        matched_key = next((k for k in target_map if k in clean_name), None)
                        if matched_key:
                            url, metadata = "", {"props": [], "ua": "Mozilla/5.0"}
                            for line in lines[1:]:
                                if line.startswith('http'): url = line.strip()
                                elif line.startswith('#'):
                                    metadata['props'].append(line.strip())
                                    if 'User-Agent=' in line: metadata['ua'] = line.split('=')[1]

                            # block_link.txt এ থাকা কোনো কিছু থাকলে বাদ দিবে
                            if any(b in url for b in blocked_keywords): continue
                            
                            if url:
                                if matched_key not in candidate_links: candidate_links[matched_key] = []
                                candidate_links[matched_key].append({"url": url, "meta": metadata})
            except: continue

        # ২. সেরা লিঙ্ক বাছাই (Buffer-less selection)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        final_list = []

        for target_key, links in candidate_links.items():
            tasks = [get_latency(semaphore, session, l['url'], {'User-Agent': l['meta']['ua']}) for l in links]
            latencies = await asyncio.gather(*tasks)
            
            best_idx = -1
            min_lat = float('inf')
            for i, lat in enumerate(latencies):
                if lat < min_lat:
                    min_lat = lat
                    best_idx = i
            
            if best_idx != -1:
                best = links[best_idx]
                final_list.append({
                    "name": target_map[target_key]["raw_name"],
                    "logo": target_map[target_key]["logo"],
                    "url": best["url"],
                    "props": best["meta"]["props"]
                })

        # ৩. ফাইনাল প্লেলিস্ট রাইটিং (কোনো ডুপ্লিকেট থাকবে না)
        with open("playlist.m3u", "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in final_list:
                f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}", {item["name"]}\n')
                for prop in item["props"]:
                    f.write(f"{prop}\n")
                f.write(f"{item['url']}\n")

    print(f"Update Done! Total Unique Channels: {len(final_list)}")

if __name__ == "__main__":
    asyncio.run(main())
