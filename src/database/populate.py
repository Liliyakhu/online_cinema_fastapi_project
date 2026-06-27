import asyncio

from sqlalchemy import select

from database.session_postgresql import AsyncPostgresqlSessionLocal
from database.models.accounts import UserGroupModel, UserGroupEnum, UserModel
from database.models.movies import MovieModel, DirectorModel, StarModel, GenreModel, CertificationModel


async def create_default_groups() -> None:
    async with AsyncPostgresqlSessionLocal() as session:
        for group_name in UserGroupEnum:
            stmt = select(UserGroupModel).where(UserGroupModel.name == group_name)
            result = await session.execute(stmt)
            if not result.scalars().first():
                session.add(UserGroupModel(name=group_name))
        await session.commit()


async def create_test_users() -> None:
    async with AsyncPostgresqlSessionLocal() as session:
        for email, password, group_name in [
            ("admin@admin.com", "Admin123&", UserGroupEnum.ADMIN),
            ("user@user.com", "User123$", UserGroupEnum.USER),
        ]:
            stmt = select(UserModel).where(UserModel.email == email)
            result = await session.execute(stmt)
            if not result.scalars().first():
                stmt = select(UserGroupModel).where(UserGroupModel.name == group_name)
                result = await session.execute(stmt)
                user_group = result.scalars().first()
                user = UserModel.create(
                    email=email,
                    raw_password=password,
                    group_id=user_group.id
                )
                user.is_active = True
                session.add(user)
        await session.commit()


async def create_test_movies() -> None:
    async with AsyncPostgresqlSessionLocal() as session:
        stmt = select(MovieModel).where(MovieModel.name == "Inception")
        result = await session.execute(stmt)
        if result.scalars().first():
            return

        certification = CertificationModel(name="PG-13")
        session.add(certification)
        await session.flush()

        genre_action = GenreModel(name="Action")
        genre_scifi = GenreModel(name="Sci-Fi")
        genre_crime = GenreModel(name="Crime")
        genre_drama = GenreModel(name="Drama")
        session.add_all([genre_action, genre_scifi, genre_crime, genre_drama])
        await session.flush()

        star_dicaprio = StarModel(name="Leonardo DiCaprio")
        star_bale = StarModel(name="Christian Bale")
        star_ledger = StarModel(name="Heath Ledger")
        session.add_all([star_dicaprio, star_bale, star_ledger])
        await session.flush()

        director_nolan = DirectorModel(name="Christopher Nolan")
        session.add(director_nolan)
        await session.flush()

        inception = MovieModel(
            name="Inception",
            year=2010,
            imdb=8.8,
            price=9.99,
            time=148,
            votes=1309038,
            meta_score=74,
            gross=836800000,
            description="A thief who steals corporate secrets through "
                        "use of dream-sharing technology is given the inverse "
                        "task of planting an idea into the mind of a CEO.",
            certification_id=certification.id,
            genres=[genre_action, genre_scifi],
            stars=[star_dicaprio],
            directors=[director_nolan],
        )

        dark_knight = MovieModel(
            name="The Dark Knight",
            year=2008,
            imdb=9.0,
            price=9.99,
            time=152,
            votes=2900000,
            meta_score=84,
            gross=1006000000,
            description="When the menace known as the Joker wreaks havoc "
                        "and chaos on the people of Gotham, the caped crusader "
                        "must come to terms with one of the greatest psychological "
                        "tests of his ability to fight injustice.",
            certification_id=certification.id,
            genres=[genre_crime, genre_drama],
            stars=[star_bale, star_ledger],
            directors=[director_nolan],
        )

        session.add_all([inception, dark_knight])
        await session.commit()


async def main():
    await create_default_groups()
    await create_test_users()
    await create_test_movies()


if __name__ == "__main__":
    asyncio.run(main())
