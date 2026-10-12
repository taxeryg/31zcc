import requests, time, json

BASE = 'http://127.0.0.1:5000'

# 1. Data uret
print('[1] Hesap bilgileri uretiliyor...')
r = requests.post(BASE + '/api/account-creator/generate-data', json={'use_temp_mail': True}, timeout=25)
if r.status_code != 200:
    print('  HATA:', r.status_code, r.text[:200])
    exit(1)
data = r.json()
print('  Kullanici:', data.get('username'))
print('  Email    :', data.get('email'))
print('  Sifre    :', data.get('password'))
print('  Dogum    :', data.get('birthdate'))

if not data.get('email'):
    print('  [UYARI] Email alinamadi:', data.get('temp_mail_error'))

# 2. Hesap olustur
print()
print('[2] Hesap olusturma baslatiliyor (headless=True)...')
r2 = requests.post(BASE + '/api/account-creator/start', json={
    'username': data.get('username'),
    'email': data.get('email'),
    'password': data.get('password'),
    'birthdate': data.get('birthdate'),
    'use_temp_mail': True,
    'headless': True
}, timeout=30)
print('  HTTP:', r2.status_code)
result = r2.json()
print('  Sonuc:', json.dumps(result, ensure_ascii=False, indent=2))
print()
print('Hesap olusturma arkaplanda calistirildi.')
print('Loglar icin dashboard.js veya /api/account-creator/status kontrol edin.')
