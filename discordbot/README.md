# TaxerAI Discord Bot

Discord slash komutlarıyla Kick chat botunu yönet.

## Kurulum

### 1. Discord Bot Oluştur
1. https://discord.com/developers/applications adresine git
2. **New Application** → isim gir
3. **Bot** sekmesi → **Add Bot**
4. **TOKEN** kısmından token kopyala
5. **Privileged Gateway Intents** → hepsini aç
6. **OAuth2 → URL Generator** → ot + pplications.commands seç
7. Bot Permissions: Send Messages, Embed Links, Use Slash Commands
8. Oluşan URL ile botu sunucuna ekle

### 2. .env Dosyasını Düzenle
`.env
DISCORD_TOKEN=bot_tokenin_buraya
FLASK_API_URL=http://localhost:5000
GUILD_ID=discord_sunucu_id_buraya
`
> Guild ID: Discord sunucuna sağ tıkla → Sunucu ID'sini Kopyala

### 3. Botu Başlat
`ash
cd discordbot
python bot.py
`

---

## Komutlar

### /tokenadd tokens:<tokenlar>
Kick Bearer tokenlarını toplu ekle. Alt alta yapıştır.

**Örnek:**
`
/tokenadd tokens:eyJhbGciOiJSUzI1NiJ9...
eyJhbGciOiJSUzI1NiJ9...
eyJhbGciOiJSUzI1NiJ9...
`

---

### /chatbot username message amount spam emotes duration
Kick chate otomatik mesaj gönder.

| Parametre | Açıklama | Örnek |
|-----------|----------|-------|
| username | Kick kanal adı veya Chatroom ID | hakancaihanoglu |
| message | Gönderilecek mesaj | discordgg/kickbot |
| mount | Kaç hesap kullanılsın (0=hepsi) | 10 |
| spam | Sürekli tekrarlansın mı | True |
| emotes | Emote eklensin mi | True |
| duration | Spam süresi (saniye) | 15 |

**Örnek:**
`
/chatbot username hakancaihanoglu message discordgg/kickbot amount 10 spam True emotes True duration 15
`

---

### /stopbot
Çalışan chatbot oturumunu durdur.

### /status
Bot ve bağlı hesap durumunu göster.
