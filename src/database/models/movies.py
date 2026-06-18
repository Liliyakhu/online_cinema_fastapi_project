import uuid as uuid_module

from typing import Optional
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import (
    UUID,
    Integer,
    String,
    Float,
    Text,
    DECIMAL,
    UniqueConstraint,
    ForeignKey,
    Table,
    Column,
    DateTime
)
from sqlalchemy.orm import mapped_column, Mapped, relationship

from database.models.base import Base


MoviesGenresModel = Table(
    "movies_genres",
    Base.metadata,
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True, nullable=False),
    Column(
        "genre_id",
        ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True, nullable=False),
)

StarsMoviesModel = Table(
    "movie_stars",
    Base.metadata,
    Column(
        "movie_id",
        ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True, nullable=False),
    Column(
        "star_id",
        ForeignKey("stars.id", ondelete="CASCADE"), primary_key=True, nullable=False),
)

MoviesDirectorsModel = Table(
    "movie_directors",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("director_id", ForeignKey("directors.id", ondelete="CASCADE"), primary_key=True),
)


FavoritesModel = Table(
    "favorites",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
)


class GenreModel(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    movies: Mapped[list["MovieModel"]] = relationship(
        "MovieModel",
        secondary=MoviesGenresModel,
        back_populates="genres"
    )

    def __repr__(self):
        return f"<Genre(name='{self.name}')>"


class StarModel(Base):
    __tablename__ = "stars"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    movies: Mapped[list["MovieModel"]] = relationship(
        "MovieModel",
        secondary=StarsMoviesModel,
        back_populates="stars"
    )

    def __repr__(self):
        return f"<Star(name='{self.name}')>"


class CertificationModel(Base):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    movies: Mapped[list["MovieModel"]] = relationship("MovieModel", back_populates="certification")

    def __repr__(self):
        return f"<Certification(name='{self.name}')>"


class DirectorModel(Base):
    __tablename__ = "directors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    movies: Mapped[list["MovieModel"]] = relationship(
        "MovieModel",
        secondary=MoviesDirectorsModel,
        back_populates="directors"
    )

    def __repr__(self):
        return f"<Director(name='{self.name}')>"


class MovieModel(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    imdb: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    uuid: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid_module.uuid4,
        nullable=False,
        unique=True
    )
    time: Mapped[int] = mapped_column(nullable=False)
    votes: Mapped[int] = mapped_column(nullable=False)
    meta_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    gross: Mapped[Optional[float]] = mapped_column(nullable=True)
    price: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    certification_id: Mapped[int] = mapped_column(ForeignKey("certifications.id"), nullable=False)
    certification: Mapped["CertificationModel"] = relationship("CertificationModel", back_populates="movies")
    genres: Mapped[list["GenreModel"]] = relationship(
        "GenreModel",
        secondary=MoviesGenresModel,
        back_populates="movies"
    )

    stars: Mapped[list["StarModel"]] = relationship(
        "StarModel",
        secondary=StarsMoviesModel,
        back_populates="movies"
    )

    directors: Mapped[list["DirectorModel"]] = relationship(
        "DirectorModel",
        secondary=MoviesDirectorsModel,
        back_populates="movies"
    )

    favorited_by: Mapped[list["UserModel"]] = relationship(
        "UserModel",
        secondary=FavoritesModel,
        back_populates="favorite_movies"
    )

    likes: Mapped[list["MovieLikeModel"]] = relationship("MovieLikeModel", back_populates="movie")

    __table_args__ = (
        UniqueConstraint("name", "year", "time", name="unique_movie_constraint"),
    )

    @classmethod
    def default_order_by(cls):
        return [cls.id.desc()]

    def __repr__(self):
        return f"<Movie(name='{self.name}', year={self.year}, imdb={self.imdb})>"


class MovieLikeModel(Base):
    __tablename__ = "movie_likes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    is_like: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    user: Mapped["UserModel"] = relationship("UserModel")
    movie: Mapped["MovieModel"] = relationship("MovieModel", back_populates="likes")

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="unique_user_movie_like"),
    )

