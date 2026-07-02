import firebase_admin
from firebase_admin import auth, credentials

cred = credentials.Certificate("secrets/firebase-auth.json")  # ajuste o caminho
firebase_admin.initialize_app(cred)

UID = "GmFZnYPzTeZ6CkSmQCfvVCrhQp62"
auth.set_custom_user_claims(UID, {"role": "admin"})
print("OK — claim definida")