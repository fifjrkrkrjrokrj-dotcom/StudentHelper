# Study Helper Bot

A smart Telegram bot for students to manipulate PDFs and Images.
Deployable on any generic hosting platform like Railway, Heroku, or a VPS.

## Features
- **Image to PDF**: Send multiple images and compile them into a single PDF.
- **PDF to Image**: Extract all pages of a PDF into separate images.
- **PDF Layout Optimizer**: 
  - 1-in-1 B&W or Color Invert
  - 2-in-1 Landscape
  - 2-in-1 Portrait
  - 4-in-1 Grid

## Local Setup
1. Clone the repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your details.
4. Run the bot: `python main.py`

## Deploy on Railway
1. Push this repository to GitHub.
2. Go to [Railway](https://railway.app/).
3. Create a new project from your GitHub repo.
4. Go to the Variables tab and add `API_ID`, `API_HASH`, and `BOT_TOKEN`.
5. Railway will automatically detect the `Procfile` and deploy the bot.

## Deploy on Heroku
1. Push this repository to GitHub.
2. Create a new Heroku app.
3. Connect your GitHub repo.
4. Go to Settings > Config Vars and add `API_ID`, `API_HASH`, and `BOT_TOKEN`.
5. Deploy the branch. Go to Resources tab and ensure the `worker` dyno is turned on.

## Deploy on VPS (Ubuntu)
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
git clone <your-repo-url> study-bot
cd study-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
nano .env
```

Use `pm2` or `systemd` to run it in the background:
```bash
sudo npm install -g pm2
pm2 start main.py --name study-bot --interpreter=./venv/bin/python
pm2 save
pm2 startup
```
