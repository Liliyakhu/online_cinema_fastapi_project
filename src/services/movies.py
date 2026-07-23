from typing import Optional, Literal, List

from fastapi import HTTPException, status
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database.models.accounts import UserModel, UserGroupEnum
from database.models.movies import (
    MovieModel, GenreModel, StarModel, DirectorModel, CertificationModel,
    MovieLikeModel, MovieRatingModel, MovieCommentModel, CommentLikeModel,
    MoviesGenresModel, MoviesDirectorsModel, StarsMoviesModel,
)
from database.models.notifications import NotificationModel
from database.models.cart import CartItemModel
from schemas import (
    MovieListResponseSchema, MovieListItemSchema, MovieCreateSchema,
    MovieDetailSchema, MovieUpdateSchema, MovieLikeRequestSchema,
    MovieLikeResponseSchema, MovieRatingRequestSchema, MovieRatingResponseSchema,
    CommentCreateSchema, CommentResponseSchema, GenreWithCountSchema,
    GenreSchema, GenreCreateSchema, StarSchema, StarCreateSchema,
    DirectorSchema, DirectorCreateSchema, CertificationSchema,
    CertificationCreateSchema, MessageResponseSchema,
)


class MovieService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _check_moderator_permission(self, user_id: int) -> None:
        result = await self.db.execute(
            select(UserModel).options(joinedload(UserModel.group)).filter_by(id=user_id)
        )
        current_user = result.scalars().first()
        if not current_user or not (
            current_user.has_group(UserGroupEnum.MODERATOR) or
            current_user.has_group(UserGroupEnum.ADMIN)
        ):
            raise HTTPException(status_code=403, detail="No permission.")

    def _build_movie_list_response(
        self, movies, total_items, page, per_page, base_url
    ) -> MovieListResponseSchema:
        total_pages = (total_items + per_page - 1) // per_page
        return MovieListResponseSchema(
            items=[MovieListItemSchema.model_validate(m) for m in movies],
            total=total_items,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            prev_page=f"{base_url}?page={page - 1}&per_page={per_page}" if page > 1 else None,
            next_page=f"{base_url}?page={page + 1}&per_page={per_page}" if page < total_pages else None,
        )

    async def get_movie_list(
        self,
        page: int,
        per_page: int,
        search: Optional[str],
        genre_id: Optional[int],
        year: Optional[int],
        sort_by: Optional[Literal["price", "year", "imdb", "votes"]],
        sort_order: Literal["asc", "desc"],
    ) -> MovieListResponseSchema:
        base_stmt = select(MovieModel)

        if search:
            base_stmt = (
                base_stmt
                .outerjoin(MovieModel.stars)
                .outerjoin(MovieModel.directors)
                .where(or_(
                    MovieModel.name.ilike(f"%{search}%"),
                    MovieModel.description.ilike(f"%{search}%"),
                    StarModel.name.ilike(f"%{search}%"),
                    DirectorModel.name.ilike(f"%{search}%"),
                ))
            )

        if genre_id:
            base_stmt = base_stmt.join(MovieModel.genres).where(GenreModel.id == genre_id)

        if year:
            base_stmt = base_stmt.where(MovieModel.year == year)

        base_stmt = base_stmt.distinct()

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_items = (await self.db.execute(count_stmt)).scalar() or 0

        if not total_items:
            raise HTTPException(status_code=404, detail="No movies found.")

        stmt = base_stmt.options(
            joinedload(MovieModel.genres),
            joinedload(MovieModel.certification),
        )

        sortable_fields = {
            "price": MovieModel.price,
            "year": MovieModel.year,
            "imdb": MovieModel.imdb,
            "votes": MovieModel.votes,
        }

        if sort_by:
            column = sortable_fields[sort_by]
            stmt = stmt.order_by(column.desc() if sort_order == "desc" else column.asc())
        else:
            order_by = MovieModel.default_order_by()
            if order_by:
                stmt = stmt.order_by(*order_by)

        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        movies = (await self.db.execute(stmt)).scalars().unique().all()

        if not movies:
            raise HTTPException(status_code=404, detail="No movies found.")

        return self._build_movie_list_response(
            movies, total_items, page, per_page, "/api/v1/cinema/movies/"
        )

    async def get_favorites(
        self,
        user_id: int,
        page: int,
        per_page: int,
        search: Optional[str],
        genre_id: Optional[int],
        year: Optional[int],
        sort_by: Optional[Literal["price", "year", "imdb", "votes"]],
        sort_order: Literal["asc", "desc"],
    ) -> MovieListResponseSchema:
        base_stmt = (
            select(MovieModel)
            .join(MovieModel.favorited_by)
            .where(UserModel.id == user_id)
            .distinct()
        )

        if search:
            base_stmt = (
                base_stmt
                .outerjoin(MovieModel.stars)
                .outerjoin(MovieModel.directors)
                .where(or_(
                    MovieModel.name.ilike(f"%{search}%"),
                    MovieModel.description.ilike(f"%{search}%"),
                    StarModel.name.ilike(f"%{search}%"),
                    DirectorModel.name.ilike(f"%{search}%"),
                ))
            )

        if genre_id:
            base_stmt = base_stmt.join(MovieModel.genres).where(GenreModel.id == genre_id)

        if year:
            base_stmt = base_stmt.where(MovieModel.year == year)

        base_stmt = base_stmt.distinct()
        total_items = (await self.db.execute(
            select(func.count()).select_from(base_stmt.subquery())
        )).scalar() or 0

        if not total_items:
            raise HTTPException(status_code=404, detail="No favorite movies found.")

        stmt = base_stmt.options(
            joinedload(MovieModel.genres),
            joinedload(MovieModel.certification),
        )

        sortable_fields = {
            "price": MovieModel.price,
            "year": MovieModel.year,
            "imdb": MovieModel.imdb,
            "votes": MovieModel.votes,
        }

        if sort_by:
            column = sortable_fields[sort_by]
            stmt = stmt.order_by(column.desc() if sort_order == "desc" else column.asc())
        else:
            order_by = MovieModel.default_order_by()
            if order_by:
                stmt = stmt.order_by(*order_by)

        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        movies = (await self.db.execute(stmt)).scalars().unique().all()

        return self._build_movie_list_response(
            movies, total_items, page, per_page, "/api/v1/cinema/movies/favorites/"
        )

    async def get_movie(
        self, movie_id: int, user_id: Optional[int]
    ) -> MovieDetailSchema:
        result = await self.db.execute(
            select(MovieModel)
            .where(MovieModel.id == movie_id)
            .options(
                joinedload(MovieModel.certification),
                joinedload(MovieModel.genres),
                joinedload(MovieModel.stars),
                joinedload(MovieModel.directors),
            )
        )
        movie = result.unique().scalar_one_or_none()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

        likes_count = (await self.db.execute(
            select(func.count()).select_from(MovieLikeModel).where(
                MovieLikeModel.movie_id == movie_id, MovieLikeModel.is_like == True
            )
        )).scalar() or 0

        dislikes_count = (await self.db.execute(
            select(func.count()).select_from(MovieLikeModel).where(
                MovieLikeModel.movie_id == movie_id, MovieLikeModel.is_like == False
            )
        )).scalar() or 0

        average_rating = (await self.db.execute(
            select(func.avg(MovieRatingModel.rating)).where(MovieRatingModel.movie_id == movie_id)
        )).scalar()

        total_ratings = (await self.db.execute(
            select(func.count()).select_from(MovieRatingModel).where(MovieRatingModel.movie_id == movie_id)
        )).scalar() or 0

        user_like = None
        user_rating = None
        if user_id:
            user_like = (await self.db.execute(
                select(MovieLikeModel.is_like).where(
                    MovieLikeModel.movie_id == movie_id,
                    MovieLikeModel.user_id == user_id,
                )
            )).scalar_one_or_none()

            user_rating = (await self.db.execute(
                select(MovieRatingModel.rating).where(
                    MovieRatingModel.movie_id == movie_id,
                    MovieRatingModel.user_id == user_id,
                )
            )).scalar_one_or_none()

        movie_data = MovieDetailSchema.model_validate(movie)
        movie_data.likes_count = likes_count
        movie_data.dislikes_count = dislikes_count
        movie_data.average_rating = round(average_rating, 1) if average_rating else None
        movie_data.total_ratings = total_ratings
        movie_data.user_like = user_like
        movie_data.user_rating = user_rating

        return movie_data

    async def create_movie(
        self, movie_data: MovieCreateSchema, user_id: int
    ) -> MovieDetailSchema:
        await self._check_moderator_permission(user_id)

        cert = await self.db.get(CertificationModel, movie_data.certification_id)
        if not cert:
            raise HTTPException(status_code=404, detail="Certification not found.")

        genres = (await self.db.execute(
            select(GenreModel).where(GenreModel.id.in_(movie_data.genre_ids))
        )).scalars().all()
        if len(genres) != len(movie_data.genre_ids):
            raise HTTPException(status_code=404, detail="One or more genres not found.")

        stars = (await self.db.execute(
            select(StarModel).where(StarModel.id.in_(movie_data.star_ids))
        )).scalars().all()
        if len(stars) != len(movie_data.star_ids):
            raise HTTPException(status_code=404, detail="One or more stars not found.")

        directors = (await self.db.execute(
            select(DirectorModel).where(DirectorModel.id.in_(movie_data.director_ids))
        )).scalars().all()
        if len(directors) != len(movie_data.director_ids):
            raise HTTPException(status_code=404, detail="One or more directors not found.")

        movie = MovieModel(
            name=movie_data.name,
            year=movie_data.year,
            time=movie_data.time,
            imdb=movie_data.imdb,
            votes=movie_data.votes,
            meta_score=movie_data.meta_score,
            gross=movie_data.gross,
            description=movie_data.description,
            price=movie_data.price,
            certification_id=movie_data.certification_id,
            genres=genres,
            stars=stars,
            directors=directors,
        )
        self.db.add(movie)
        await self.db.commit()
        await self.db.refresh(movie)

        result = await self.db.execute(
            select(MovieModel)
            .options(
                joinedload(MovieModel.certification),
                joinedload(MovieModel.genres),
                joinedload(MovieModel.stars),
                joinedload(MovieModel.directors),
            )
            .filter_by(id=movie.id)
        )
        return MovieDetailSchema.model_validate(result.scalars().unique().first())

    async def update_movie(
        self, movie_id: int, movie_data: MovieUpdateSchema, user_id: int
    ) -> MovieDetailSchema:
        await self._check_moderator_permission(user_id)

        movie_result = await self.db.execute(
            select(MovieModel)
            .options(
                joinedload(MovieModel.genres),
                joinedload(MovieModel.stars),
                joinedload(MovieModel.directors),
            )
            .filter_by(id=movie_id)
        )
        movie = movie_result.unique().scalar_one_or_none()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

        update_data = movie_data.model_dump(exclude_unset=True)

        if "genre_ids" in update_data:
            genres = (await self.db.execute(
                select(GenreModel).where(GenreModel.id.in_(update_data.pop("genre_ids")))
            )).scalars().all()
            movie.genres = genres

        if "star_ids" in update_data:
            stars = (await self.db.execute(
                select(StarModel).where(StarModel.id.in_(update_data.pop("star_ids")))
            )).scalars().all()
            movie.stars = stars

        if "director_ids" in update_data:
            directors = (await self.db.execute(
                select(DirectorModel).where(DirectorModel.id.in_(update_data.pop("director_ids")))
            )).scalars().all()
            movie.directors = directors

        if "certification_id" in update_data:
            cert = await self.db.get(CertificationModel, update_data["certification_id"])
            if not cert:
                raise HTTPException(status_code=404, detail="Certification not found.")

        for field, value in update_data.items():
            setattr(movie, field, value)

        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(status_code=400, detail="Invalid input data.")

        result = await self.db.execute(
            select(MovieModel)
            .options(
                joinedload(MovieModel.certification),
                joinedload(MovieModel.genres),
                joinedload(MovieModel.stars),
                joinedload(MovieModel.directors),
            )
            .filter_by(id=movie.id)
        )
        return MovieDetailSchema.model_validate(result.scalars().unique().first())

    async def delete_movie(self, movie_id: int, user_id: int) -> None:
        await self._check_moderator_permission(user_id)

        movie = await self.db.get(MovieModel, movie_id)
        if not movie:
            raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

        cart_count = (await self.db.execute(
            select(func.count()).select_from(CartItemModel).where(CartItemModel.movie_id == movie_id)
        )).scalar() or 0
        if cart_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete movie: it exists in {cart_count} user cart(s)."
            )

        await self.db.delete(movie)
        await self.db.commit()

    async def add_to_favorites(self, movie_id: int, user_id: int) -> MessageResponseSchema:
        result = await self.db.execute(
            select(UserModel).options(joinedload(UserModel.favorite_movies)).filter_by(id=user_id)
        )
        current_user = result.unique().scalars().first()

        movie = await self.db.get(MovieModel, movie_id)
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found.")

        if movie in current_user.favorite_movies:
            raise HTTPException(status_code=409, detail="Movie already in favorites.")

        current_user.favorite_movies.append(movie)
        await self.db.commit()
        return MessageResponseSchema(message="Movie added to favorites.")

    async def remove_from_favorites(self, movie_id: int, user_id: int) -> MessageResponseSchema:
        result = await self.db.execute(
            select(UserModel).options(joinedload(UserModel.favorite_movies)).filter_by(id=user_id)
        )
        current_user = result.unique().scalars().first()

        movie = await self.db.get(MovieModel, movie_id)
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found.")

        if movie not in current_user.favorite_movies:
            raise HTTPException(status_code=409, detail="Movie is not in favorites.")

        current_user.favorite_movies.remove(movie)
        await self.db.commit()
        return MessageResponseSchema(message="Movie deleted from favorites.")

    async def like_movie(
        self, movie_id: int, data: MovieLikeRequestSchema, user_id: int
    ) -> MovieLikeResponseSchema:
        movie = await self.db.get(MovieModel, movie_id)
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found.")

        existing_like = (await self.db.execute(
            select(MovieLikeModel).where(
                MovieLikeModel.movie_id == movie_id,
                MovieLikeModel.user_id == user_id,
            )
        )).scalars().first()

        if not existing_like:
            self.db.add(MovieLikeModel(user_id=user_id, movie_id=movie_id, is_like=data.is_like))
        elif existing_like.is_like == data.is_like:
            await self.db.delete(existing_like)
        else:
            existing_like.is_like = data.is_like

        await self.db.commit()

        likes_count = (await self.db.execute(
            select(func.count()).select_from(MovieLikeModel).where(
                MovieLikeModel.movie_id == movie_id, MovieLikeModel.is_like == True
            )
        )).scalar() or 0

        dislikes_count = (await self.db.execute(
            select(func.count()).select_from(MovieLikeModel).where(
                MovieLikeModel.movie_id == movie_id, MovieLikeModel.is_like == False
            )
        )).scalar() or 0

        user_like = (await self.db.execute(
            select(MovieLikeModel.is_like).where(
                MovieLikeModel.movie_id == movie_id,
                MovieLikeModel.user_id == user_id,
            )
        )).scalar_one_or_none()

        return MovieLikeResponseSchema(
            likes_count=likes_count,
            dislikes_count=dislikes_count,
            user_like=user_like,
        )

    async def rate_movie(
        self, movie_id: int, data: MovieRatingRequestSchema, user_id: int
    ) -> MovieRatingResponseSchema:
        movie = await self.db.get(MovieModel, movie_id)
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found.")

        existing_rating = (await self.db.execute(
            select(MovieRatingModel).where(
                MovieRatingModel.movie_id == movie_id,
                MovieRatingModel.user_id == user_id,
            )
        )).scalars().first()

        if not existing_rating:
            self.db.add(MovieRatingModel(user_id=user_id, movie_id=movie_id, rating=data.rating))
        else:
            existing_rating.rating = data.rating

        await self.db.commit()

        avg = (await self.db.execute(
            select(func.avg(MovieRatingModel.rating)).where(MovieRatingModel.movie_id == movie_id)
        )).scalar() or 0

        total = (await self.db.execute(
            select(func.count()).select_from(MovieRatingModel).where(MovieRatingModel.movie_id == movie_id)
        )).scalar() or 0

        user_rating = (await self.db.execute(
            select(MovieRatingModel.rating).where(
                MovieRatingModel.movie_id == movie_id,
                MovieRatingModel.user_id == user_id,
            )
        )).scalar_one_or_none()

        return MovieRatingResponseSchema(average_rating=avg, total_ratings=total, user_rating=user_rating)

    async def create_comment(
        self, movie_id: int, data: CommentCreateSchema, user_id: int
    ) -> CommentResponseSchema:
        movie = await self.db.get(MovieModel, movie_id)
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found.")

        parent_id = data.parent_id if data.parent_id and data.parent_id > 0 else None

        if parent_id:
            parent_comment = await self.db.get(MovieCommentModel, parent_id)
            if not parent_comment or parent_comment.movie_id != movie_id:
                raise HTTPException(status_code=404, detail="Parent comment not found.")
            if parent_comment.parent_id:
                raise HTTPException(status_code=400, detail="Cannot reply to a reply.")
            if parent_comment.user_id != user_id:
                self.db.add(NotificationModel(
                    user_id=parent_comment.user_id,
                    message="Your comment received a new reply.",
                ))

        comment = MovieCommentModel(
            user_id=user_id, movie_id=movie_id, parent_id=parent_id, text=data.text
        )
        self.db.add(comment)
        await self.db.commit()
        await self.db.refresh(comment)

        result = await self.db.execute(
            select(MovieCommentModel)
            .where(MovieCommentModel.id == comment.id)
            .options(joinedload(MovieCommentModel.replies))
        )
        return CommentResponseSchema.model_validate(result.unique().scalar_one())

    async def get_comments(self, movie_id: int) -> List[CommentResponseSchema]:
        movie = await self.db.get(MovieModel, movie_id)
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found.")

        result = await self.db.execute(
            select(MovieCommentModel)
            .where(
                MovieCommentModel.movie_id == movie_id,
                MovieCommentModel.parent_id.is_(None),
            )
            .options(joinedload(MovieCommentModel.replies).joinedload(MovieCommentModel.replies))
            .order_by(MovieCommentModel.created_at.desc())
        )
        return [CommentResponseSchema.model_validate(c) for c in result.unique().scalars().all()]

    async def like_comment(self, comment_id: int, user_id: int) -> MessageResponseSchema:
        comment = await self.db.get(MovieCommentModel, comment_id)
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found.")

        existing_like = (await self.db.execute(
            select(CommentLikeModel).where(
                CommentLikeModel.comment_id == comment_id,
                CommentLikeModel.user_id == user_id,
            )
        )).scalars().first()

        if existing_like:
            await self.db.delete(existing_like)
            await self.db.commit()
            return MessageResponseSchema(message="Comment unliked.")

        self.db.add(CommentLikeModel(user_id=user_id, comment_id=comment_id))

        if comment.user_id != user_id:
            self.db.add(NotificationModel(
                user_id=comment.user_id,
                message="Your comment received a new like.",
            ))

        await self.db.commit()
        return MessageResponseSchema(message="Comment liked.")

    async def get_genres(self) -> List[GenreWithCountSchema]:
        stmt = (
            select(GenreModel.id, GenreModel.name, func.count(MoviesGenresModel.c.movie_id).label("movies_count"))
            .outerjoin(MoviesGenresModel, GenreModel.id == MoviesGenresModel.c.genre_id)
            .group_by(GenreModel.id)
            .order_by(GenreModel.name)
        )
        rows = (await self.db.execute(stmt)).all()
        return [GenreWithCountSchema(id=r.id, name=r.name, movies_count=r.movies_count) for r in rows]

    async def create_genre(self, data: GenreCreateSchema) -> GenreSchema:
        if (await self.db.execute(select(GenreModel).where(GenreModel.name == data.name))).scalars().first():
            raise HTTPException(status_code=409, detail="Genre already exists.")
        genre = GenreModel(name=data.name)
        self.db.add(genre)
        await self.db.commit()
        await self.db.refresh(genre)
        return GenreSchema.model_validate(genre)

    async def update_genre(self, genre_id: int, data: GenreCreateSchema, user_id: int) -> GenreSchema:
        await self._check_moderator_permission(user_id)
        genre = await self.db.get(GenreModel, genre_id)
        if not genre:
            raise HTTPException(status_code=404, detail="Genre not found.")
        if (await self.db.execute(
            select(GenreModel).where(GenreModel.name == data.name, GenreModel.id != genre_id)
        )).scalars().first():
            raise HTTPException(status_code=409, detail="Genre with this name already exists.")
        genre.name = data.name
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(status_code=400, detail="Invalid input data.")
        await self.db.refresh(genre)
        return GenreSchema.model_validate(genre)

    async def delete_genre(self, genre_id: int, user_id: int) -> None:
        await self._check_moderator_permission(user_id)
        genre = await self.db.get(GenreModel, genre_id)
        if not genre:
            raise HTTPException(status_code=404, detail="Genre not found.")
        movies_count = (await self.db.execute(
            select(func.count()).select_from(MoviesGenresModel).where(MoviesGenresModel.c.genre_id == genre_id)
        )).scalar() or 0
        if movies_count > 0:
            raise HTTPException(status_code=409, detail="Cannot delete genre that is used by at least one movie.")
        await self.db.delete(genre)
        await self.db.commit()

    async def create_star(self, data: StarCreateSchema) -> StarSchema:
        if (await self.db.execute(select(StarModel).where(StarModel.name == data.name))).scalars().first():
            raise HTTPException(status_code=409, detail="Star already exists.")
        star = StarModel(name=data.name)
        self.db.add(star)
        await self.db.commit()
        await self.db.refresh(star)
        return StarSchema.model_validate(star)

    async def update_star(self, star_id: int, data: StarCreateSchema, user_id: int) -> StarSchema:
        await self._check_moderator_permission(user_id)
        star = await self.db.get(StarModel, star_id)
        if not star:
            raise HTTPException(status_code=404, detail="Star not found.")
        if (await self.db.execute(
            select(StarModel).where(StarModel.name == data.name, StarModel.id != star_id)
        )).scalars().first():
            raise HTTPException(status_code=409, detail="Star with this name already exists.")
        star.name = data.name
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(status_code=400, detail="Invalid input data.")
        await self.db.refresh(star)
        return StarSchema.model_validate(star)

    async def delete_star(self, star_id: int, user_id: int) -> None:
        await self._check_moderator_permission(user_id)
        star = await self.db.get(StarModel, star_id)
        if not star:
            raise HTTPException(status_code=404, detail="Star not found.")
        movies_count = (await self.db.execute(
            select(func.count()).select_from(StarsMoviesModel).where(StarsMoviesModel.c.star_id == star_id)
        )).scalar() or 0
        if movies_count > 0:
            raise HTTPException(status_code=409, detail="Cannot delete star that is used by at least one movie.")
        await self.db.delete(star)
        await self.db.commit()

    async def create_director(self, data: DirectorCreateSchema) -> DirectorSchema:
        if (await self.db.execute(select(DirectorModel).where(DirectorModel.name == data.name))).scalars().first():
            raise HTTPException(status_code=409, detail="Director already exists.")
        director = DirectorModel(name=data.name)
        self.db.add(director)
        await self.db.commit()
        await self.db.refresh(director)
        return DirectorSchema.model_validate(director)

    async def update_director(self, director_id: int, data: DirectorCreateSchema, user_id: int) -> DirectorSchema:
        await self._check_moderator_permission(user_id)
        director = await self.db.get(DirectorModel, director_id)
        if not director:
            raise HTTPException(status_code=404, detail="Director not found.")
        if (await self.db.execute(
            select(DirectorModel).where(DirectorModel.name == data.name, DirectorModel.id != director_id)
        )).scalars().first():
            raise HTTPException(status_code=409, detail="Director with this name already exists.")
        director.name = data.name
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(status_code=400, detail="Invalid input data.")
        await self.db.refresh(director)
        return DirectorSchema.model_validate(director)

    async def delete_director(self, director_id: int, user_id: int) -> None:
        await self._check_moderator_permission(user_id)
        director = await self.db.get(DirectorModel, director_id)
        if not director:
            raise HTTPException(status_code=404, detail="Director not found.")
        movies_count = (await self.db.execute(
            select(func.count()).select_from(MoviesDirectorsModel).where(
                MoviesDirectorsModel.c.director_id == director_id
            )
        )).scalar() or 0
        if movies_count > 0:
            raise HTTPException(status_code=409, detail="Cannot delete director that is used by at least one movie.")
        await self.db.delete(director)
        await self.db.commit()

    async def create_certification(self, data: CertificationCreateSchema) -> CertificationSchema:
        if (await self.db.execute(
            select(CertificationModel).where(CertificationModel.name == data.name)
        )).scalars().first():
            raise HTTPException(status_code=409, detail="Certification already exists.")
        cert = CertificationModel(name=data.name)
        self.db.add(cert)
        await self.db.commit()
        await self.db.refresh(cert)
        return CertificationSchema.model_validate(cert)
