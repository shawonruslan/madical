# Wafid Monitor (GitHub Actions + Telegram)

শুধু দেখে, কিছু বুক বা submit করে না। wafid-এর booking পেজ থেকে প্রতিটা দেশের জন্য auto assign-এ এখন কোন সেন্টার আছে সেটা পড়ে, আর Telegram-এ জানায়:
- সেন্টার বদলালে: আগের সেন্টার কতক্ষণ ছিল, নতুন কোনটা এল, আর গড়ে কতক্ষণ পরপর বদলায়
- টার্গেট সেন্টার এলে: **GOOD TIME TO BOOK** বার্তা
- প্রতি ঘণ্টায় (বা যেটা ঠিক করবেন) সব দেশের অবস্থা

## ১. Telegram bot
1. Telegram-এ **@BotFather**-কে `/newbot` পাঠান। নাম দিন, একটা token পাবেন (যেমন `123456:ABC...`)।
2. নিজের bot-কে যেকোনো একটা মেসেজ পাঠান।
3. ব্রাউজারে খুলুন: `https://api.telegram.org/bot<TOKEN>/getUpdates`। সেখানে `"chat":{"id":123456789` থেকে সংখ্যাটা নিন। এটাই chat id। (group-এ চাইলে bot-কে group-এ যোগ করে group-এ মেসেজ দিন, id হবে `-100...`)

## ২. GitHub repo
1. নতুন repo খুলুন, এই ফোল্ডারের সব ফাইল push করুন (`.github` সহ)।
2. **Settings > Secrets and variables > Actions**
   - **Secrets** ট্যাব: `TG_TOKEN` = bot token, `TG_CHAT_ID` = chat id
   - **Variables** ট্যাব:
     - `TARGETS` = টার্গেট সেন্টার। যেমন `SA=10600|10734` (একাধিক দেশ: `SA=10600|10734,KW=6136`, যেকোনো দেশ: `10600`)
     - `INTERVAL_SEC` (ঐচ্ছিক) = কত সেকেন্ড পরপর চেক, default `30`, সবচেয়ে কম `30`
     - `SUMMARY_MINUTES` (ঐচ্ছিক) = কত মিনিট পরপর সারাংশ, default `60`, বন্ধ করতে `0`

## ৩. চালানো
**Actions** ট্যাব > **Wafid monitor** > **Run workflow**। `run_minutes`-এ কত মিনিট দেখবে লিখুন (সর্বোচ্চ 350, প্রায় ৬ ঘণ্টা)। চালু হলেই Telegram-এ "Wafid monitor started" আসবে।

workflow-এ প্রতিদিন সকাল ৯টায় (BD) নিজে থেকে একবার চলার ব্যবস্থাও আছে। না চাইলে `monitor.yml` থেকে `schedule` অংশটা মুছে দিন।

আগের run-এর ইতিহাস cache-এ থাকে, তাই "গড়ে কতক্ষণ পরপর বদলায়" হিসাবটা প্রতি run-এ আরও ঠিক হয়।

## জানা দরকার
- **খরচ:** private repo-তে GitHub মাসে ২০০০ মিনিট ফ্রি দেয়। ২ ঘণ্টার এক run মানে ১২০ মিনিট। public repo-তে মিনিটের সীমা নেই, আর secrets তখনও গোপন থাকে।
- GitHub Actions সারাক্ষণ চালু রাখার server নয়। একটানা ২৪ ঘণ্টা চালানোর জন্য বারবার run দেওয়া GitHub-এর নিয়মের বাইরে যেতে পারে। দরকারের সময় run দিন।
- GitHub-এর server-এর IP wafid আটকে দিলে Telegram-এ "site not responding" আসবে।
