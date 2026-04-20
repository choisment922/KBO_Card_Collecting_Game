# config.py — 민감 정보 설정 파일
# ⚠️  이 파일은 절대 Git에 올리지 마세요 (.gitignore에 추가하세요)

# Flask 세션 암호화 키 — 길고 랜덤한 문자열로 바꾸세요
# 터미널에서 생성: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = "17108c673c5fa420b9017ce050d96eb32e99f3e778fa9ddd1e5cc9a2c5becbcf"

# Google Cloud Console에서 발급한 OAuth 2.0 자격증명
# https://console.cloud.google.com → API 및 서비스 → 사용자 인증 정보
GOOGLE_CLIENT_ID = "your_id"
GOOGLE_CLIENT_SECRET = "your_client_secret"
