# coding: utf-8

# Standard Libraries
import datetime
from pathlib import Path

# Third Party Libraries
from peewee import BooleanField
from peewee import CharField
from peewee import DateTimeField
from peewee import DoesNotExist
from peewee import ForeignKeyField
from peewee import IntegerField
from peewee import Model
from peewee import PrimaryKeyField
from peewee import TextField
from peewee import Using
from playhouse.sqliteq import SqliteQueueDatabase

# Dopplerr
from dopplerr.singleton import singleton


# pylint: disable=invalid-name
class Events(Model):
    timestamp = DateTimeField(default=datetime.datetime.now)
    type = CharField()
    message = TextField()


class SeriesMedias(Model):
    id = PrimaryKeyField()
    tv_db_id = IntegerField(null=True)
    season_number = IntegerField(null=True)
    episode_number = IntegerField(null=True)
    added_timestamp = DateTimeField(default=datetime.datetime.now)
    series_title = CharField(null=True)
    episode_title = CharField(null=True)
    quality = CharField(null=True)
    video_languages = CharField(null=True)
    dirty = BooleanField(default=True)
    media_filename = TextField(null=False, index=True)


class SeriesSubtitles(Model):
    added_timestamp = DateTimeField(default=datetime.datetime.now)
    series_media = ForeignKeyField(SeriesMedias, related_name='subtitles')
    language = CharField()


# pylint: enable=invalid-name


@singleton
class DopplerrDb(object):

    def __init__(self):
        self.__sqlite_db_path = None
        self.__conn = None
        self.__database = None

    @property
    def database(self):
        if not self.__database:
            self.__database = SqliteQueueDatabase(
                self.__sqlite_db_path, pragmas=(('foreign_keys', 'on'), ))
        return self.__database

    @property
    def conn(self):
        return self.database.get_conn()

    def init(self, sqlite_db_path: Path, reset_db=False):
        self.__sqlite_db_path = sqlite_db_path.as_posix()
        if reset_db:
            sqlite_db_path.unlink()

    def create_tables(self):
        self.database.create_table(Events, safe=True)
        self.database.create_table(SeriesSubtitles, safe=True)
        self.database.create_table(SeriesMedias, safe=True)

    def insert_event(self, thetype: str, message: str):
        with Using(self.database, [Events], with_transaction=False):
            Events.create(type=thetype, message=message)

    def get_recent_events(self, limit: int):
        with Using(self.database, [Events], with_transaction=False):
            events = (Events.select().limit(limit).order_by(Events.timestamp.desc()).execute())
            return [{
                "timestamp": e.timestamp.strftime('%Y-%m-%dT%H:%M:%S'),
                "type": e.type,
                "message": e.message
            } for e in events]

    def update_series_media(self,
                            series_title,
                            tv_db_id,
                            season_number,
                            episode_number,
                            episode_title,
                            quality,
                            video_languages,
                            media_filename,
                            dirty=True):
        assert media_filename, "media_filename cannot be None"
        with Using(self.database, [SeriesMedias], with_transaction=False):
            media, _ = self._get_or_create(
                SeriesMedias,
                tv_db_id=tv_db_id,
                season_number=season_number,
                episode_number=episode_number,
                media_filename=media_filename)
            media.series_title = series_title
            media.episode_title = episode_title
            media.quality = quality
            media.video_languages = video_languages
            media.dirty = dirty
            media.media_filename = media_filename
            media.save()

    @staticmethod
    def _get_or_create(model, **kwargs):
        try:
            it = model.get(**kwargs)
            return it, False
        except DoesNotExist:
            it = model.create(**kwargs)
            return it, True

    def update_fetched_series_subtitles(self, series_episode_uid, subtitles_languages, dirty=True):
        with Using(self.database, [SeriesMedias, SeriesSubtitles], with_transaction=False):
            media = (SeriesMedias.select().where(
                SeriesMedias.tv_db_id == series_episode_uid.tv_db_id,
                SeriesMedias.season_number == series_episode_uid.season_number,
                SeriesMedias.episode_number == series_episode_uid.episode_number))
            for lang in subtitles_languages:
                self._get_or_create(
                    SeriesSubtitles,
                    series_media=media,
                    language=lang,
                )
            for m in media:
                m.dirty = dirty
                m.save()

    def get_last_fetched_series(self, limit: int):
        with Using(self.database, [SeriesMedias, SeriesSubtitles], with_transaction=False):
            events = (SeriesSubtitles.select().order_by(
                SeriesSubtitles.added_timestamp.desc()).limit(limit).execute())
            return [{
                "added_timestamp": e.added_timestamp.strftime('%Y-%m-%dT%H:%M:%S'),
                "series_title": e.series_media.series_title,
                "season_number": e.series_media.season_number,
                "episode_number": e.series_media.episode_number,
                "episode_title": e.series_media.episode_title,
                "quality": e.series_media.quality,
                "video_languages": e.series_media.video_languages,
                "subtitle_language": e.language,
            } for e in events]

    def get_medias_series(self):
        with Using(self.database, [SeriesMedias, SeriesSubtitles], with_transaction=False):
            limit = 100
            medias = (SeriesMedias.select().order_by(
                SeriesMedias.series_title.desc()).limit(limit).execute())
            return [{
                "added_timestamp": med.added_timestamp.strftime('%Y-%m-%dT%H:%M:%S'),
                "series_title": med.series_title,
                "season_number": med.season_number,
                "episode_number": med.episode_number,
                "episode_title": med.episode_title,
                "quality": med.quality,
                "video_languages": med.video_languages,
                "subtitle_languages": sorted(s.language for s in med.subtitles),
                "dirty": med.dirty,
            } for med in medias]

    def media_exists(self, media_filename):
        with Using(self.database, [SeriesMedias], with_transaction=False):
            medias = (SeriesMedias.select(SeriesMedias.media_filename)
                      .where(SeriesMedias.media_filename == media_filename)).execute()
            return bool(medias)
