from enum import Enum


class Links(Enum):
    STANDART = [
        # YouTube
        "https://www.youtube.com/",
        "https://youtube.com/",
        "https://m.youtube.com/",
        "https://youtu.be/",
        "https://www.youtube.com/shorts/",
        "https://youtube.com/shorts/",
        # TikTok
        "https://www.tiktok.com/",
        "https://vt.tiktok.com/",
        "https://vm.tiktok.com/",
        # Instagram
        "https://www.instagram.com/",
        "https://instagram.com/",
        # Twitter (X) — desktop + mobile
        "https://x.com/",
        "https://twitter.com/",
        "https://mobile.twitter.com/",
        "https://mobile.x.com/",
        # Facebook
        "https://www.facebook.com/reel/",
        "https://www.facebook.com/share/",
    ]


class VideoStatusMessages(Enum):
    VideoProcessing = "<code>{url}</code>\n\n⏳ Videoingiz qayta ishlanmoqda..."
    VideoSuccess = "<code>{url}</code>\n\n✅ Video muvaffaqiyatli yuklab olindi. Yuborilmoqda..."
    VideoHostRedirect = (
        "⚠️ Video hajmi Telegram orqali yuborish uchun juda katta.\n"
        "Biz uni vaqtincha serverimizda saqlab turamiz. Zarur bo'lsa yuklab oling:\n\n"
        "{download_url}\n\n"
        "<b><i>downloaded via @secondsaverbot</i></b>"
    )
    VideoError = "⚠️ Yuklab olishda xatolik yuz berdi. Havola noto'g'ri bo'lishi yoki video o'chirilgan bo'lishi mumkin."
    Caption = "<b><i><a href='https://t.me/secondsaverbot'>via</a> | <a href='{url}'>link</a> | <a href='https://l.rhmt.uz/BTZs72'>donate</a></i></b>"


class ProgressState(Enum):
    PREPARING = "Tayyorlanmoqda"
    VIDEO_DOWNLOADING = "Video yuklanmoqda"
    AUDIO_DOWNLOADING = "Audio yuklanmoqda"
    FINALIZING = "Yakunlanmoqda"