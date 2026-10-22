# 🌐 Deploying Victim App to GitHub & Render.com (Live Cloud Demo)

This guide explains how to deploy **ONLY the Victim App** to the cloud using **GitHub + Render.com (100% Free)**, while keeping your **ML models, monitoring API, and React dashboard safely running on your localhost**.

---

## 🏗️ Architecture

```
                       [ Public Internet ]
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
       Attack Traffic                   Metrics Polling
 (simulate_attack.py)               (monitoring_api/api.py)
               │                               ▲
               │                               │
               ▼                               │
    ┌─────────────────────┐                    │
    │  ☁️ RENDER.COM       │                    │
    │  Victim Web App     ├────────────────────┘
    │  (Flask + Gunicorn) │
    │  https://...onrender.com
    └─────────────────────┘

────────────────────────────────────────────────────────────
 [ Your Local Machine (Localhost) ]

    ┌─────────────────────┐         ┌─────────────────────┐
    │  🛡️ Monitoring API  │◄───────►│ 📊 React Dashboard  │
    │  (Port 5000)        │         │ (Port 5173)         │
    │  + Isolation Forest │         │ Real-time UI        │
    │  + Adaptive Baseline│         └─────────────────────┘
    └─────────────────────┘
```

---

## 🚀 Step 1: Initialize Git inside `victim_app`

Open a terminal or PowerShell in `d:\Sample\Project-II\Demo\victim_app`:

```bash
cd d:\Sample\Project-II\Demo\victim_app
git init
git add .
git commit -m "Initial commit of Victim Web App for DDoS Demo"
```

---

## 🐙 Step 2: Push to a New GitHub Repository

1. Go to **[GitHub](https://github.com)** and create a new repository:
   - Repository name: `ddos-victim-app`
   - Set visibility to **Public**
   - Do **NOT** initialize with README or .gitignore
2. Run the commands shown by GitHub:
   ```bash
   git branch -M main
   git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/ddos-victim-app.git
   git push -u origin main
   ```

---

## ☁️ Step 3: Deploy Free on Render.com (3 Minutes)

1. Open **[https://render.com](https://render.com)** and sign in with your GitHub account.
2. Click **New +** (top right) $\rightarrow$ Select **Web Service**.
3. Choose **Build and deploy from a Git repository** $\rightarrow$ Click **Next**.
4. Select your **`ddos-victim-app`** repository.
5. Fill in the deployment settings:
   - **Name**: `ddos-victim-app` (or your choice)
   - **Region**: `Singapore` (or closest region)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: **Free**
6. Click **Create Web Service**.
7. In ~2 minutes, Render will build and launch your application and provide a live URL:
   ```
   https://ddos-victim-app.onrender.com
   ```
8. Test the live URL in your browser:
   - `https://ddos-victim-app.onrender.com/` (TechDaily News homepage)
   - `https://ddos-victim-app.onrender.com/health` (Returns `{"status": "healthy"}`)
   - `https://ddos-victim-app.onrender.com/metrics` (Returns traffic JSON)

---

## 🔗 Step 4: Connect Local Monitoring API to Live Victim App

Before starting your local monitoring API, point it to your live Render URL using the `VICTIM_HOST` environment variable:

### In PowerShell:
```powershell
$env:VICTIM_HOST="https://ddos-victim-app.onrender.com"
python monitoring_api/api.py
```

### In Command Prompt (CMD):
```cmd
set VICTIM_HOST=https://ddos-victim-app.onrender.com
python monitoring_api/api.py
```

You will see:
```
[Capture] Monitoring remote victim at https://ddos-victim-app.onrender.com
```

---

## 💥 Step 5: Launch Attack Simulation Against the Live Server

When conducting your demo, launch attack traffic over the internet directly to the cloud-deployed victim:

### In PowerShell:
```powershell
$env:VICTIM_URL="https://ddos-victim-app.onrender.com/api/data"
python attack_sim/simulate_attack.py rate-limit 40 25
```

### In CMD:
```cmd
set VICTIM_URL=https://ddos-victim-app.onrender.com/api/data
python attack_sim/simulate_attack.py rate-limit 40 25
```

---

## 🎬 Review 3 Demonstration Sequence

1. **Show the Live Cloud App**:
   - Open `https://ddos-victim-app.onrender.com` on the projector.
   - Reviewers can even open it on their mobile phones!
2. **Show the Local Security Dashboard**:
   - Open `http://localhost:5173`.
   - Status shows `NORMAL` (Green) while pulling live metrics across the internet.
3. **Launch the Attack**:
   - Run `python attack_sim/simulate_attack.py single-ip-flood 35 25`.
   - Within 3 seconds, the dashboard turns `ATTACK` (Red).
   - Autonomous mitigation engages.
4. **Demonstrate Failure Mode (Protect Victim Switch)**:
   - Toggle **Protect Victim** to `OFF` in the dashboard.
   - Re-run the attack or refresh the live Render site.
   - The cloud victim returns `503 Service Unavailable`.
   - Toggle **Protect Victim** back `ON` $\rightarrow$ Server recovers instantly!
