import asyncio
import aiohttp
import pyzipper
import os
import re

ZIP_PASS = os.getenv('ZIP_PASSWORD')
MAX_CONCURRENT = 500 

async def check_link(semaphore, session, name, url):
    async with semaphore:
        try:
            async with session.head(url, timeout=3, allow_redirects=True) as response:
                if response.status == 200:
                    return name, url
        except:
            return None

async def main():
    # ফাইল নাম links.zip হতে হবে
    zip_path = 'links.zip'
    if not os.path.exists(zip_path):
        # যদি আপনি tera.zip নামই রাখতে চান তবে এখানে পরিবর্তন করুন
        if os.path.exists('tera.zip'):
            zip_path = 'tera.zip'
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

    unique_channels = {}
    async with aiohttp.ClientSession() as session:
        for m3u_url in sources:
            try:
                async with session.get(m3u_url, timeout=10) as response:
                    text = await response.text()
                    matches = re.finditer(r'#EXTINF:.*?,(.*?)\n(http.*)', text)
                    for match in matches:
                        n, l = match.group(1).strip(), match.group(2).strip()
                        if n not in unique_channels:
                            unique_channels[n] = l
            except:
                continue

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [check_link(semaphore, session, n, l) for n, l in unique_channels.items()]
        results = await asyncio.gather(*tasks)

        # ফাইলটি অবশ্যই তৈরি হতে হবে
        with open("playlist.m3u", "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for res in results:
                if res:
                    f.write(f"#EXTINF:-1, {res[0]}\n{res[1]}\n")
    
    print("Playlist created successfully!")

if __name__ == "__main__":
    asyncio.run(main())
