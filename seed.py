# seed.py
from app.db.session import SessionLocal, engine
from app.models.role import Role, RoleName
from app.db.base_class import Base

def seed_roles():
    print("Seeding database roles...")
    db = SessionLocal()
    try:
        # Check if roles already exist to avoid duplicates
        existing_role = db.query(Role).first()
        if existing_role:
            print("Database already has roles. Skipping seed.")
            return

        # Define the default roles matching your RoleName Enum
        roles_to_create = [
            Role(id=1, name=RoleName.ADMIN),
            Role(id=2, name=RoleName.MANAGER),
            Role(id=3, name=RoleName.USER)
        ]
        
        db.add_all(roles_to_create)
        db.commit()
        print("Successfully seeded roles: ADMIN (1), MANAGER (2), USER (3)")
        
    except Exception as e:
        db.rollback()
        print(f"Error seeding roles: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_roles()