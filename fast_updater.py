import asyncio
import aiohttp
import pyzipper
import os
import re

# GitHub Secrets থেকে জিপ পাসওয়ার্ড নিবে
ZIP_PASS = os.getenv('ZIP_PASSWORD')

# একসাথে কতগুলো লিঙ্ক চেক করবে (৫০০-১০০০ পর্যন্ত নিরাপদ)
MAX_CONCURRENT = 500 

async def check_link(semaphore, session, name, url):
    """লিঙ্কটি সচল কি না তা হেড রিকোয়েস্টের মাধ্যমে চেক করে"""
    async with semaphore:
        try:
            # শুধু হেডার চেক করবে, ভিডিও ডাউনলোড করবে না
            async with session.head(url, timeout=3, allow_redirects=True) as response:
                if response.status == 200:
                    return name, url
        except:
            return None

async def main():
    # ১. জিপ ফাইল রিড করা
    if not os.path.exists('links.zip'):
        print("Error: links.zip ফাইলটি পাওয়া যায়নি!")
        return

    try:
        with pyzipper.AESZipFile('links.zip') as zf:
            zf.setpassword(ZIP_PASS.encode('utf-8'))
            
            # sources.txt থেকে প্লেলিস্ট ইউআরএল পড়া
            with zf.open('sources.txt') as f:
                sources = [line.decode('utf-8').strip() for line in f if line.strip()]
            
            # targets.txt থেকে পছন্দের চ্যানেলের নাম পড়া (যদি থাকে)
            targets = []
            if 'targets.txt' in zf.namelist():
                with zf.open('targets.txt') as f:
                    targets = [line.decode('utf-8').strip().lower() for line in f if line.strip()]
    except Exception as e:
        print(f"Zip Error: {e}")
        return

    unique_channels = {}
    
    async with aiohttp.ClientSession() as session:
        # ২. প্লেলিস্টগুলো থেকে লিঙ্ক এক্সট্র্যাক্ট করা
        for m3u_url in sources:
            try:
                async with session.get(m3u_url, timeout=10) as response:
                    text = await response.text()
                    # হাই-স্পিড রেজিক্স দিয়ে নাম ও লিঙ্ক আলাদা করা
                    matches = re.finditer(r'#EXTINF:.*?,(.*?)\n(http.*)', text)
                    for match in matches:
                        raw_name = match.group(1).strip()
                        clean_name = raw_name.lower()
                        link = match.group(2).strip()
                        
                        # যদি টার্গেট লিস্ট থাকে, তবে শুধু সেই চ্যানেলগুলো নিবে
                        if targets:
                            if any(t in clean_name for t in targets):
                                if clean_name not in unique_channels:
                                    unique_channels[clean_name] = (raw_name, link)
                        else:
                            # টার্গেট লিস্ট না থাকলে সব ইউনিক চ্যানেল নিবে
                            if clean_name not in unique_channels:
                                unique_channels[clean_name] = (raw_name, link)
            except:
                continue

        # ৩. লিঙ্কগুলো দ্রুত চেক করা (Asyncio ব্যবহার করে)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [check_link(semaphore, session, data[0], data[1]) for data in unique_channels.values()]
        
        print(f"Total Channels to Check: {len(tasks)}")
        results = await asyncio.gather(*tasks)

        # ৪. ফাইনাল প্লেলিস্ট (m3u) ফাইল তৈরি করা
        with open("playlist.m3u", "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            active_count = 0
            for res in results:
                if res:
                    f.write(f"#EXTINF:-1, {res[0]}\n{res[1]}\n")
                    active_count += 1
        
        print(f"Update Complete! Active Channels Found: {active_count}")

if __name__ == "__main__":
    asyncio.run(main())
