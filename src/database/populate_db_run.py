import asyncio
from src.database.populate_db import seed_movies, seed_user_groups, seed_users, seed_orders
from src.database.session_db import AsyncSessionLocal  
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database import UserGroupModel, UserGroupEnum

async def main():
    

    async with AsyncSessionLocal() as session: 
        exists = await session.execute(
            select(UserGroupModel).where(UserGroupModel.name == UserGroupEnum.ADMIN)
        )
        if exists.scalar_one_or_none():
            return
        
        await seed_user_groups(session)
        await seed_movies(session)
        await seed_users(session)
        await seed_orders(session)
        await session.commit()
        print("✅ DB seeded successfully!")

if __name__ == "__main__":
    asyncio.run(main())
