import os
import unittest

from bson.objectid import ObjectId
from datetime import datetime
from mock import patch
from mongoengine import connect

from config.config import Config
from dao import Dao
from model import *
import rankings

# mongomock currently has issues with MongoEngine:
# (https://github.com/MongoEngine/mongoengine/issues/1045)
# should switch back to mongomock after resolved
DATABASE_NAME = 'garpr_test'
CONFIG_LOCATION = os.path.abspath(os.path.dirname(__file__) + '/../config/config.ini')

delta = .001

class TestRankings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super(TestRankings, cls).setUpClass()

        config = Config(CONFIG_LOCATION)
        cls.conn = connect(DATABASE_NAME)
        cls.conn.the_database.authenticate(config.get_db_user(),
                                       config.get_db_password(),
                                       source=config.get_auth_db_name())
        cls.conn.drop_database(DATABASE_NAME)

    def setUp(self):
        self.norcal = Region(id='norcal', display_name='Norcal')
        self.socal = Region(id='socal', display_name='Socal')
        self.texas = Region(id='texas', display_name='Texas')
        self.norcal.save()
        self.socal.save()
        self.texas.save()

        self.dao = Dao('norcal')

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
                name='shroomed',
                ratings=[
                    Rating.from_trueskill(self.norcal, trueskill.Rating())],
                regions=[self.norcal])
        self.player_5 = Player(
                name='pewpewu',
                ratings=[
                    Rating.from_trueskill(self.norcal, trueskill.Rating())],
                regions=[self.norcal, self.socal])
        self.player_1.save()
        self.player_2.save()
        self.player_3.save()
        self.player_4.save()
        self.player_5.save()

        self.players = [self.player_1, self.player_2, self.player_3, self.player_4, self.player_5]

        self.tournament_name_1 = 'tournament 1'
        self.tournament_type_1 = 'tio'
        self.tournament_date_1 = datetime(2013, 10, 16)
        self.tournament_regions_1 = [self.norcal]
        self.tournament_raw_1 = 'raw1'
        self.tournament_players_1 = [self.player_1, self.player_2, self.player_3, self.player_4]
        self.tournament_matches_1 = [
                Match(winner=self.player_1, loser=self.player_2),
                Match(winner=self.player_3, loser=self.player_4)
        ]

        # tournament 2 is earlier than tournament 1, but inserted after
        self.tournament_name_2 = 'tournament 2'
        self.tournament_type_2 = 'challonge'
        self.tournament_date_2 = datetime(2013, 10, 10)
        self.tournament_regions_2 = [self.norcal]
        self.tournament_raw_2 = 'raw2'
        self.tournament_players_2 = [self.player_5, self.player_2, self.player_3, self.player_4]
        self.tournament_matches_2 = [
                Match(winner=self.player_5, loser=self.player_2),
                Match(winner=self.player_3, loser=self.player_4)
        ]


        self.tournament_1 = Tournament(
                    name=self.tournament_name_1,
                    source_type=self.tournament_type_1,
                    date=self.tournament_date_1,
                    regions=self.tournament_regions_1,
                    raw=self.tournament_raw_1,
                    players=self.tournament_players_1,
                    matches=self.tournament_matches_1)
        self.tournament_2 = Tournament(
                    name=self.tournament_name_2,
                    source_type=self.tournament_type_2,
                    date=self.tournament_date_2,
                    regions=self.tournament_regions_2,
                    raw=self.tournament_raw_2,
                    players=self.tournament_players_2,
                    matches=self.tournament_matches_2)
        self.tournament_1.save()
        self.tournament_2.save()

        self.tournaments = [self.tournament_1, self.tournament_2]

    def tearDown(self):
        self.conn.drop_database(DATABASE_NAME)

    # all tournaments are within the active range and will be included
    def test_generate_rankings(self):
        now = datetime(2013, 10, 17)

        # assert rankings before they get reset
        self.assertEquals(self.dao.get_player_by_id(self.player_1.id).ratings, self.player_1.ratings)
        self.assertEquals(self.dao.get_player_by_id(self.player_2.id).ratings, self.player_2.ratings)
        self.assertEquals(self.dao.get_player_by_id(self.player_3.id).ratings, self.player_3.ratings)
        self.assertEquals(self.dao.get_player_by_id(self.player_4.id).ratings, self.player_4.ratings)
        self.assertEquals(self.dao.get_player_by_id(self.player_5.id).ratings, self.player_5.ratings)

        rankings.generate_ranking(self.dao, now=now, day_limit=30, num_tourneys=1)
        # assert rankings after ranking calculation
        self.assertAlmostEquals(self.dao.get_player_by_id(self.player_1.id).get_rating(self.norcal).mu,
                                28.458, delta=delta)
        self.assertAlmostEquals(self.dao.get_player_by_id(self.player_1.id).get_rating(self.norcal).sigma,
                                7.201, delta=delta)
        self.assertAlmostEquals(self.dao.get_player_by_id(self.player_2.id).get_rating(self.norcal).mu,
                                18.043, delta=delta)
        self.assertAlmostEquals(self.dao.get_player_by_id(self.player_2.id).get_rating(self.norcal).sigma,
                                6.464, delta=delta)
        self.assertAlmostEquals(self.dao.get_player_by_id(self.player_3.id).get_rating(self.norcal).mu,
                                31.230, delta=delta)
        self.assertAlmostEquals(self.dao.get_player_by_id(self.player_3.id).get_rating(self.norcal).sigma,
                                6.523, delta=delta)
        self.assertAlmostEquals(self.dao.get_player_by_id(self.player_4.id).get_rating(self.norcal).mu,
                                18.770, delta=delta)
        self.assertAlmostEquals(self.dao.get_player_by_id(self.player_4.id).get_rating(self.norcal).sigma,
                                6.523, delta=delta)
        self.assertAlmostEquals(self.dao.get_player_by_id(self.player_5.id).get_rating(self.norcal).mu,
                                29.396, delta=delta)
        self.assertAlmostEquals(self.dao.get_player_by_id(self.player_5.id).get_rating(self.norcal).sigma,
                                7.171, delta=delta)

        ranking = self.dao.get_latest_ranking()
        self.assertEquals(ranking.region, self.norcal)
        self.assertEquals(ranking.time, now)

        ranking_list = ranking.rankings

        # the ranking should not have any excluded players
        self.assertEquals(len(ranking_list), 4)

        entry = ranking_list[0]
        self.assertEquals(entry.rank, 1)
        self.assertEquals(entry.player, self.player_5)
        self.assertAlmostEquals(entry.rating.mu-3*entry.rating.sigma, 7.881, delta=delta)

        entry = ranking_list[1]
        self.assertEquals(entry.rank, 2)
        self.assertEquals(entry.player, self.player_1)
        self.assertAlmostEquals(entry.rating.mu-3*entry.rating.sigma, 6.857, delta=delta)

        entry = ranking_list[2]
        self.assertEquals(entry.rank, 3)
        self.assertEquals(entry.player, self.player_4)
        self.assertAlmostEquals(entry.rating.mu-3*entry.rating.sigma, -.800, delta=delta)

        entry = ranking_list[3]
        self.assertEquals(entry.rank, 4)
        self.assertEquals(entry.player, self.player_2)
        self.assertAlmostEquals(entry.rating.mu-3*entry.rating.sigma, -1.349, delta=delta)

    # players that only played in the first tournament will be excluded for inactivity
    def test_generate_rankings_excluded_for_inactivity(self):
        now = datetime(2013, 11, 25)

        rankings.generate_ranking(self.dao, now=now, day_limit=45, num_tourneys=1)

        ranking = self.dao.get_latest_ranking()

        ranking_list = ranking.rankings
        print ranking_list
        self.assertEquals(len(ranking_list), 3)

        entry = ranking_list[0]
        self.assertEquals(entry.rank, 1)
        self.assertEquals(entry.player, self.player_1)
        self.assertAlmostEquals(entry.rating.mu-3*entry.rating.sigma, 6.857, delta=delta)

        entry = ranking_list[1]
        self.assertEquals(entry.rank, 2)
        self.assertEquals(entry.player, self.player_4)
        self.assertAlmostEquals(entry.rating.mu-3*entry.rating.sigma, -.800, delta=delta)

        entry = ranking_list[2]
        self.assertEquals(entry.rank, 3)
        self.assertEquals(entry.player, self.player_2)
        self.assertAlmostEquals(entry.rating.mu-3*entry.rating.sigma, -1.349, delta=delta)
