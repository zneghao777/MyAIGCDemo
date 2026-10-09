from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from .config import get_settings

engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def session():
    async with Session() as db:
        try:
            yield db
        except Exception:
            keys = db.info.get("uploaded_keys", [])
            await db.rollback()
            if keys:
                from app.models import Cleanup

                async with Session() as cleanup:
                    cleanup.add(Cleanup(keys=keys))
                    await cleanup.commit()
            raise


from sqlalchemy import event
from sqlalchemy.orm import Session as SyncSession


@event.listens_for(SyncSession, "after_commit")
def forget_committed_uploads(session):
    session.info.pop("uploaded_keys", None)
