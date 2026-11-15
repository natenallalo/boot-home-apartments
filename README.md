# מאתר דירות להשכרה — רמלה ולוד

אפליקציית Streamlit לסריקת דירות/יחידות דיור מאתרי אינטרנט ו-Facebook Marketplace.

## סריקה גם כשהמחשב כבוי

GitHub Actions מריץ את `worker.py` **כל שעה** לפי `settings.json`, שומר תוצאות ב-`apartments.db`, וממשיך גם כשהמחשב המקומי כבוי.

1. שמרו הגדרות בצד באפליקציה: **שמור הגדרות לענן**
2. דחפו את `settings.json` ל-GitHub (או עדכנו ידנית ב-repo)
3. Actions → **Cloud Apartment Scan** רץ אוטומטית / ידנית

Secrets נדרשים ב-GitHub:
- `APIFY_API_TOKEN` (פייסבוק Marketplace)
- `OPENAI_API_KEY` (אופציונלי)

## הרצה מקומית

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Worker חד-פעמי / לולאה:

```bash
python worker.py
python worker.py --loop
```
