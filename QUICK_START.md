# 🚀 Raspberry Ninja Quick Start

## 1. Install (30 seconds)

```bash
curl -sSL https://raw.githubusercontent.com/steveseguin/raspberry_ninja/main/install.sh | bash
```

Choose option 1 for basic installation.

## 2. Test (10 seconds)

```bash
python3 publish.py --test
```

You should see a test pattern with bouncing ball.

## 3. Stream (5 seconds)

```bash
python3 publish.py
```

Note the stream ID shown (like `7654321`).

## 4. View

Open in any browser:
```
https://vdo.ninja/?view=7654321
```

(Replace `7654321` with your stream ID)

---

**That's it!** You're streaming.

For more options: `python3 publish.py --help`