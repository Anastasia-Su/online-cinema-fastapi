import asyncio
from src.database.populate_db import seed_movies, seed_user_groups, seed_users, seed_orders
from src.database.session_db import AsyncSessionLocal  
from sqlalchemy.ext.asyncio import AsyncSession

async def main():
    async with AsyncSessionLocal() as session: 
        
        await seed_user_groups(session)
        await seed_movies(session)
        await seed_users(session)
        await seed_orders(session)
        await session.commit()
        print("✅ DB seeded successfully!")

if __name__ == "__main__":
    asyncio.run(main())
