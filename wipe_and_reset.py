"""
wipe_and_reset.py
─────────────────
Deletes ALL documents from every Firestore collection and creates a single admin user.
Run once:  python wipe_and_reset.py
"""

from firebase_config import ALL_COLLECTIONS, USERS, db


def _delete_collection(collection_name: str) -> int:
    count = 0
    while True:
        docs = list(db.collection(collection_name).limit(400).stream())
        if not docs:
            break
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
        batch.commit()
    return count


def main():
    print("FaceAttend — wipe all Firestore data")
    print("=" * 50)
    total = 0
    for name in ALL_COLLECTIONS:
        n = _delete_collection(name)
        total += n
        print(f"  {name}: deleted {n} document(s)")
    print(f"\nTotal deleted: {total}")

    db.collection(USERS).document("admin").set({
        "email": "admin@college.edu",
        "password": "Admin@RIT2025",
        "role": "admin",
        "name": "System Administrator",
    })
    print("\nCreated admin account:")
    print("  email:    admin@college.edu")
    print("  password: Admin@RIT2025")
    print("  role:     admin")
    print("\nDone. Database is empty except the admin user.")


if __name__ == "__main__":
    main()
