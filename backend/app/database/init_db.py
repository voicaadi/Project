from app.database.connection import Base, engine
from app.database import models

Base.metadata.create_all(bind=engine)

print("Database tables created successfully!")