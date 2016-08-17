import os
import trueskill
import unittest

from bson.objectid import ObjectId
from datetime import datetime
from mongoengine import connect

from config.config import Config
from dao import Dao, verify_password
from model import *

# mongomock currently has issues with MongoEngine:
# (https://github.com/MongoEngine/mongoengine/issues/1045)
# should switch back to mongomock after resolved
DATABASE_NAME = 'garpr_test'
CONFIG_LOCATION = os.path.abspath(os.path.dirname(__file__) + '/../config/config.ini')

class TestDAO(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super(TestDAO, cls).setUpClass()

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

        self.regions = [self.norcal, self.texas]


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

        self.merge_player_1 = Player(
                name='CLGsFaT',
                aliases=['clg | sfat'],
                ratings=[
                    Rating.from_trueskill(self.norcal, trueskill.Rating())],
                regions=[self.norcal],
                merged=True,
                merge_parent=self.player_2)
        self.merge_player_1.save()
        self.player_2.merge_children.append(self.merge_player_1)
        self.player_2.save()

        # only includes players 1-3
        self.players = [self.player_1, self.player_2, self.player_3]

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
        self.tournament_regions_2 = [self.norcal, self.texas]
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

        self.pending_tournament_name_1 = 'pending tournament 1'
        self.pending_tournament_type_1 = 'tio'
        self.pending_tournament_date_1 = datetime(2013, 10, 11)
        self.pending_tournament_regions_1 = [self.norcal]
        self.pending_tournament_raw_1 = 'raw1'
        self.pending_tournament_aliases_1 = [self.player_1.name, self.player_2.name, self.player_3.name, self.player_4.name]
        self.pending_tournament_alias_matches_1 = [
                AliasMatch(winner=self.player_1.name, loser=self.player_2.name),
                AliasMatch(winner=self.player_3.name, loser=self.player_4.name)
        ]


        self.pending_tournament_1 = PendingTournament(
                    name=self.pending_tournament_name_1,
                    source_type=self.pending_tournament_type_1,
                    date=self.pending_tournament_date_1,
                    regions=self.pending_tournament_regions_1,
                    raw=self.pending_tournament_raw_1,
                    aliases=self.pending_tournament_aliases_1,
                    alias_matches=self.pending_tournament_alias_matches_1)
        self.pending_tournament_1.save()

        self.pending_tournaments = [self.pending_tournament_1]

        self.ranking_entry_1 = RankingEntry(rank=1,
                                            player=self.player_1,
                                            rating=Rating(region=self.norcal,mu=20))
        self.ranking_entry_2 = RankingEntry(rank=2,
                                            player=self.player_2,
                                            rating=Rating(region=self.norcal,mu=19))
        self.ranking_entry_3 = RankingEntry(rank=3,
                                            player=self.player_2,
                                            rating=Rating(region=self.norcal,mu=17.5))
        self.ranking_entry_4 = RankingEntry(rank=3,
                                            player=self.player_2,
                                            rating=Rating(region=self.norcal,mu=16.5))

        self.ranking_time_1 = datetime(2013, 4, 20)
        self.ranking_time_2 = datetime(2013, 4, 21)
        self.ranking_1 = Ranking(region=self.norcal,
                                 time=self.ranking_time_1,
                                 rankings=[self.ranking_entry_1, self.ranking_entry_2, self.ranking_entry_3],
                                 tournaments=self.tournaments)
        self.ranking_2 = Ranking(region=self.norcal,
                                 time=self.ranking_time_2,
                                 rankings=[self.ranking_entry_1, self.ranking_entry_2, self.ranking_entry_4],
                                 tournaments=self.tournaments)
        self.ranking_3 = Ranking(region=self.texas,
                                 time=self.ranking_time_2,
                                 rankings=[self.ranking_entry_1, self.ranking_entry_2],
                                 tournaments=self.tournaments)
        self.ranking_1.save()
        self.ranking_2.save()
        self.ranking_3.save()

        self.rankings = [self.ranking_1, self.ranking_2, self.ranking_3]

        self.user_1 = User(username='user1',
                           salt='test',
                           hashed_password='test',
                           admin_regions=[self.norcal])
        self.user_2 = User(username='user2',
                           salt='test',
                           hashed_password='test',
                           admin_regions=[self.norcal, self.texas])
        self.user_1.save()
        self.user_2.save()

        self.users = [self.user_1, self.user_2]

        self.norcal_dao = Dao('norcal')

    def tearDown(self):
        self.conn.drop_database(DATABASE_NAME)

    def test_init_with_invalid_region(self):
        # create a dao with a non existant region, should throw exception
        with self.assertRaises(Region.DoesNotExist) as cm:
            Dao('newregion')

    def test_get_all_regions(self):
        # add another region
        region = Region(id='newregion', display_name='New Region')
        region.save()

        regions = Dao.get_all_regions()
        self.assertEqual(len(regions), 4)
        self.assertEqual(regions[0], region)
        self.assertEqual(regions[1], self.norcal)
        self.assertEqual(regions[2], self.socal)
        self.assertEqual(regions[3], self.texas)

    def test_get_player_by_id(self):
        self.assertEqual(self.norcal_dao.get_player_by_id(self.player_1.id), self.player_1)
        self.assertEqual(self.norcal_dao.get_player_by_id(self.player_2.id), self.player_2)
        self.assertEqual(self.norcal_dao.get_player_by_id(self.player_3.id), self.player_3)
        self.assertIsNone(self.norcal_dao.get_player_by_id(ObjectId()))

    def test_get_player_by_alias(self):
        self.assertEqual(self.norcal_dao.get_player_by_alias('gar'), self.player_1)
        self.assertEqual(self.norcal_dao.get_player_by_alias('GAR'), self.player_1)
        self.assertEqual(self.norcal_dao.get_player_by_alias('garr'), self.player_1)
        self.assertEqual(self.norcal_dao.get_player_by_alias('sfat'), self.player_2)
        self.assertEqual(self.norcal_dao.get_player_by_alias('miom | sfat'), self.player_2)

        self.assertIsNone(self.norcal_dao.get_player_by_alias('mango'))
        self.assertIsNone(self.norcal_dao.get_player_by_alias('miom|sfat'))
        self.assertIsNone(self.norcal_dao.get_player_by_alias(''))

    def test_get_players_by_alias_from_all_regions(self):
        self.assertEqual(self.norcal_dao.get_players_by_alias_from_all_regions('gar'), [self.player_1, self.player_3])
        self.assertEqual(self.norcal_dao.get_players_by_alias_from_all_regions('GAR'), [self.player_1, self.player_3])
        self.assertEqual(self.norcal_dao.get_players_by_alias_from_all_regions('garr'), [self.player_1])
        self.assertEqual(self.norcal_dao.get_players_by_alias_from_all_regions('sfat'), [self.player_2])
        self.assertEqual(self.norcal_dao.get_players_by_alias_from_all_regions('miom | sfat'), [self.player_2])
        self.assertEqual(self.norcal_dao.get_players_by_alias_from_all_regions('mango'), [self.player_3])

        self.assertEqual(self.norcal_dao.get_players_by_alias_from_all_regions('miom|sfat'), [])
        self.assertEqual(self.norcal_dao.get_players_by_alias_from_all_regions(''), [])

    def test_get_player_id_map_from_player_aliases(self):
        aliases = ['GAR', 'sfat', 'asdf', 'mango']
        expected_map = [
            {'player_alias': 'GAR', 'player_id': self.player_1.id},
            {'player_alias': 'sfat', 'player_id': self.player_2.id},
            {'player_alias': 'asdf', 'player_id': None},
            {'player_alias': 'mango', 'player_id': None},
        ]
        map = self.norcal_dao.get_player_id_map_from_player_aliases(aliases)
        self.assertEqual(map, expected_map)

    def test_get_all_players(self):
        self.assertEqual(self.norcal_dao.get_all_players(), [self.player_1, self.player_5, self.player_2, self.player_4])

    def test_get_all_players_all_regions(self):
        self.assertEqual(self.norcal_dao.get_all_players(all_regions=True), [self.player_1, self.player_3, self.player_5, self.player_2, self.player_4])

    def test_get_all_players_include_merged(self):
        self.assertEqual(self.norcal_dao.get_all_players(include_merged=True), [self.merge_player_1, self.player_1, self.player_5, self.player_2, self.player_4])

    def test_get_all_pending_tournaments(self):
        pending_tournaments = self.norcal_dao.get_all_pending_tournaments()

        self.assertEqual(len(pending_tournaments), 1)
        self.assertEqual(pending_tournaments[0], self.pending_tournament_1)

    def test_get_all_pending_tournaments_for_region(self):
        pending_tournaments = self.norcal_dao.get_all_pending_tournaments(regions=['norcal'])

        self.assertEqual(len(pending_tournaments), 1)
        self.assertEqual(pending_tournaments[0], self.pending_tournament_1)

    def test_get_pending_tournament_by_id(self):
        pending_tournament = self.norcal_dao.get_pending_tournament_by_id(self.pending_tournament_1.id)
        self.assertEqual(pending_tournament, self.pending_tournament_1)

    def test_get_all_tournament_ids(self):
        tournament_ids = self.norcal_dao.get_all_tournament_ids()

        self.assertEqual(len(tournament_ids), 2)
        self.assertEqual(tournament_ids[0], self.tournament_2.id)
        self.assertEqual(tournament_ids[1], self.tournament_1.id)

    def test_get_all_tournaments(self):
        tournaments = self.norcal_dao.get_all_tournaments()

        self.assertEqual(len(tournaments), 2)
        # tournament 1 is last in the list because it occurs later than tournament 2
        self.assertEqual(tournaments, [self.tournament_2, self.tournament_1])

    def test_get_all_tournaments_for_region(self):
        tournaments = self.norcal_dao.get_all_tournaments(regions=[self.norcal])

        self.assertEqual(len(tournaments), 2)
        self.assertEqual(tournaments, [self.tournament_2, self.tournament_1])

        tournaments = self.norcal_dao.get_all_tournaments(regions=[self.texas])

        self.assertEqual(len(tournaments), 1)
        self.assertEqual(tournaments[0], self.tournament_2)

    def test_get_all_tournaments_containing_players(self):
        players = [self.player_5]

        tournaments = self.norcal_dao.get_all_tournaments(players=players)
        self.assertEqual(len(tournaments), 1)
        self.assertEqual(tournaments[0], self.tournament_2)

    def test_get_all_tournaments_containing_players_and_regions(self):
        players = [self.player_2]
        regions = [self.texas]

        tournaments = self.norcal_dao.get_all_tournaments(players=players, regions=regions)
        self.assertEqual(len(tournaments), 1)
        self.assertEqual(tournaments[0], self.tournament_2)

    def test_get_tournament_by_id(self):
        tournament_1 = self.norcal_dao.get_tournament_by_id(self.tournament_1.id)
        self.assertEqual(tournament_1, self.tournament_1)

        tournament_2 = self.norcal_dao.get_tournament_by_id(self.tournament_2.id)
        self.assertEqual(tournament_2, self.tournament_2)

        self.assertIsNone(self.norcal_dao.get_tournament_by_id(ObjectId()))

    def test_get_players_with_similar_alias(self):
        self.assertEqual(self.norcal_dao.get_players_with_similar_alias('gar'), [self.player_1, self.player_3])
        self.assertEqual(self.norcal_dao.get_players_with_similar_alias('GAR'), [self.player_1, self.player_3])
        self.assertEqual(self.norcal_dao.get_players_with_similar_alias('g a r'), [self.player_1, self.player_3])
        self.assertEqual(self.norcal_dao.get_players_with_similar_alias('garpr | gar'), [self.player_1, self.player_3])

        dao = self.norcal_dao
        self.assertTrue(any(player.name == "gaR" for player in dao.get_players_with_similar_alias("1 1 gar")))
        self.assertTrue(any(player.name == "gaR" for player in dao.get_players_with_similar_alias("1\t1\tgar")))
        self.assertTrue(any(player.name == "gaR" for player in dao.get_players_with_similar_alias("p1s1 gar")))
        self.assertTrue(any(player.name == "gaR" for player in dao.get_players_with_similar_alias("GOOG| gar")))
        self.assertTrue(any(player.name == "gaR" for player in dao.get_players_with_similar_alias("GOOG | gar")))
        self.assertTrue(any(player.name == "gaR" for player in dao.get_players_with_similar_alias("p1s2 GOOG| gar")))
        self.assertTrue(any(player.name == "gaR" for player in dao.get_players_with_similar_alias("garpr goog youtube gar")))

    def test_get_and_insert_merge(self):
        merge_player = Player(
                name='C9 MANGO',
                aliases=['c9 mango'],
                regions=[self.norcal, self.socal])
        merge_player.save()

        # put him in a tournament
        merge_tournament = Tournament(
            name='merge tournament',
            source_type='tio',
            date=datetime.today(),
            regions=[self.socal],
            players=[merge_player, self.player_1],
            matches=[Match(winner=merge_player, loser=self.player_1)])
        merge_tournament.save()

        the_merge = Merge(requester=self.user_1,
                          source_player=merge_player,
                          target_player=self.player_3,
                          time=datetime.today())
        self.norcal_dao.insert_merge(the_merge)

        merge_player.reload()
        self.player_3.reload()
        # check if merge actually merged players
        self.assertTrue(merge_player.merged)
        self.assertEqual(merge_player.merge_parent, self.player_3)
        self.assertTrue(merge_player in self.player_3.merge_children)
        self.assertEqual(set(self.player_3.aliases), set([u'c9 mango', u'mango', u'gar']))
        self.assertEqual(set(self.player_3.regions), set([self.norcal, self.socal]))

        # check to make sure tournament is updated
        merge_tournament.reload()
        # print self.norcal_dao.get_tournament_by_id(merge_tournament.id).players
        self.assertTrue(self.player_3 in merge_tournament.players)
        self.assertFalse(merge_player in merge_tournament.players)

    def test_get_and_undo_merge(self):
        merge_player = Player(
                name='C9 MANGO',
                aliases=['c9 mango'],
                regions=[self.norcal, self.socal])
        merge_player.save()

        # put him in a tournament
        merge_tournament = Tournament(
            name='merge tournament',
            source_type='tio',
            date=datetime.today(),
            regions=[self.socal],
            players=[merge_player, self.player_1],
            matches=[Match(winner=merge_player, loser=self.player_1)])
        merge_tournament.save()

        the_merge = Merge(requester=self.user_1,
                          source_player=merge_player,
                          target_player=self.player_3,
                          time=datetime.today())
        self.norcal_dao.insert_merge(the_merge)
        merge_id = the_merge.id

        # try to undo merge
        self.norcal_dao.undo_merge(the_merge)

        merge_player.reload()
        self.player_3.reload()

        self.assertFalse(merge_player.merged)
        self.assertIsNone(merge_player.merge_parent)
        self.assertTrue(merge_player not in self.player_3.merge_children)

        merge_tournament.reload()
        self.assertTrue(merge_player in merge_tournament.players)
        self.assertFalse(self.player_3 in merge_tournament.players)
        self.tournament_1.reload()
        self.tournament_2.reload()
        self.assertTrue(self.player_3 in self.tournament_1.players)
        self.assertTrue(self.player_3 in self.tournament_2.players)

        # test that merge was removed from list of merges
        self.assertIsNone(self.norcal_dao.get_merge(merge_id))

    # TODO: more tests for unmerge_players (bad cases)

    def test_get_nonexistent_merge(self):
        self.assertIsNone(self.norcal_dao.get_merge(ObjectId()))

    def test_get_latest_ranking(self):
        latest_ranking = self.norcal_dao.get_latest_ranking()

        self.assertEqual(latest_ranking, self.ranking_2)

    def test_get_all_users(self):
        users = self.norcal_dao.get_all_users()
        self.assertEqual(len(users), 2)
        self.assertEqual(users, self.users)

    def test_create_user(self):
        username = 'abra'
        password = 'cadabra'
        regions = [self.norcal, self.texas]
        region_ids = [self.norcal.id, self.texas.id]

        self.norcal_dao.create_user(username, password, region_ids)

        users = self.norcal_dao.get_all_users()
        self.assertEqual(len(users), 3)

        user = users[-1]
        self.assertEqual(user.username, username)
        self.assertEqual(user.admin_regions, regions)

    def test_create_user_invalid_regions(self):
        username = 'abra'
        password = 'cadabra'
        regions = ['canadia', 'bahstahn']

        with self.assertRaises(ValueError):
            self.norcal_dao.create_user(username, password, regions)

    def test_change_password(self):
        username = 'abra'
        password = 'cadabra'
        new_password = 'whoops'
        region_ids = ['norcal']

        self.norcal_dao.create_user(username, password, region_ids)
        user = self.norcal_dao.get_user_by_username_or_none(username)
        old_salt = user.salt
        old_hash = user.hashed_password
        self.assertTrue(verify_password(password, old_salt, old_hash))

        self.norcal_dao.change_passwd(username, new_password)
        new_user = self.norcal_dao.get_user_by_username_or_none(username)
        new_salt = new_user.salt
        new_hash = new_user.hashed_password

        self.assertNotEquals(old_salt, new_salt)
        self.assertTrue(verify_password(new_password, new_salt, new_hash))
