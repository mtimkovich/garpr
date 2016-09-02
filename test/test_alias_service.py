import os
import trueskill
import unittest

from bson.objectid import ObjectId
from datetime import datetime
from mongoengine import connect

from config.config import Config
from dao import Dao, verify_password
from model import *

import alias_service


DATABASE_NAME = 'garpr_test'
CONFIG_LOCATION = 'config/config.ini'

class TestAliasService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super(TestAliasService, cls).setUpClass()

        config = Config(CONFIG_LOCATION)
        cls.conn = connect(DATABASE_NAME)
        cls.conn.the_database.authenticate(config.get_db_user(),
                                       config.get_db_password(),
                                       source=config.get_auth_db_name())
        cls.conn.drop_database(DATABASE_NAME)

    def setUp(self):
        self.maxDiff = None

        self.norcal = Region(id='norcal', display_name='Norcal')
        self.socal = Region(id='socal', display_name='Socal')
        self.texas = Region(id='texas', display_name='Texas')
        self.norcal.save()
        self.socal.save()
        self.texas.save()

        self.player_1 = Player(
                name='gaR',
                aliases=['gar', 'garr'],
                ratings=[
                    Rating.from_trueskill(self.norcal, trueskill.Rating()),
                    Rating.from_trueskill(self.texas, trueskill.Rating())],
                regions=[self.norcal, self.texas])
        self.player_2 = Player(
                name='sfat',
                aliases=['sfat', 'miom | sfat'],
                ratings=[
                    Rating.from_trueskill(self.norcal, trueskill.Rating())],
                regions=[self.norcal])
        self.player_3 = Player(
                name='mango',
                aliases=['mango', 'gar'],
                ratings=[
                    Rating.from_trueskill(self.norcal, trueskill.Rating(mu=2, sigma=3))],
                regions=[self.socal])
        self.player_4 = Player(
                name='garpr|gar',
                aliases=['garpr|gar'],
                ratings=[
                    Rating.from_trueskill(self.norcal, trueskill.Rating(mu=2, sigma=3))],
                regions=[self.norcal])
        self.player_1.save()
        self.player_2.save()
        self.player_3.save()
        self.player_4.save()

        self.players = [self.player_1, self.player_2, self.player_3, self.player_4]

        self.user_1 = User(username='user1',
                           salt='test',
                           hashed_password='test',
                           admin_regions=[self.norcal])
        self.user_1.save()
        self.users = [self.user_1]

        self.norcal_dao = Dao('norcal')

    def tearDown(self):
        self.conn.drop_database(DATABASE_NAME)

    def test_get_top_suggestion_for_aliases(self):
        suggestions = alias_service.get_top_suggestion_for_aliases(self.norcal_dao, ['gar', 'garpr | gar'])
        expected_suggestions = {
            "gar": self.player_1,
            "garpr | gar": self.player_1,
        }

        self.assertEquals(suggestions, expected_suggestions)

    def test_get_top_suggestion_for_aliases_none(self):
        suggestions = alias_service.get_top_suggestion_for_aliases(self.norcal_dao, ['gar', 'garpr | gar', 'ASDFASDF'])
        expected_suggestions = {
            "gar": self.player_1,
            "garpr | gar": self.player_1,
            "ASDFASDF": None
        }

        self.assertEquals(suggestions, expected_suggestions)

    def test_get_alias_to_id_map_in_list_format(self):
        suggestions = alias_service.get_alias_mappings(
                self.norcal_dao, ['gar', 'garpr | gar', 'ASDFASDF'])

        self.assertEquals(len(suggestions), 3)
