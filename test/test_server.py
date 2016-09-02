import base64
import hashlib
import json
import mongomock
import os
import requests
import string
import subprocess
import trueskill
import unittest

from bson.objectid import ObjectId
from datetime import datetime
from mock import patch, Mock
from mongoengine import connect

import alias_service
import dao
import rankings
import server

from config.config import Config
from dao import Dao
from model import *
from scraper.tio import TioScraper

NORCAL_FILES = [('test/data/norcal1.tio', 'Singles'), ('test/data/norcal2.tio', 'Singles Pro Bracket')]
TEXAS_FILES = [('test/data/texas1.tio', 'singles'), ('test/data/texas2.tio', 'singles')]
NORCAL_PENDING_FILES = [('test/data/pending1.tio', 'bam 6 singles')]

NORCAL_REGION_NAME = 'norcal'
TEXAS_REGION_NAME = 'texas'

# mongomock currently has issues with MongoEngine:
# (https://github.com/MongoEngine/mongoengine/issues/1045)
# should switch back to mongomock after resolved
DATABASE_DUMP_FILE = 'garpr_test_dump'
DATABASE_NAME = 'garpr_test'
CONFIG_LOCATION = os.path.abspath(os.path.dirname(__file__) + '/../config/config.ini')

def connect_test_db():
    config = Config(CONFIG_LOCATION)
    conn = connect(DATABASE_NAME)
    conn.the_database.authenticate(config.get_db_user(),
                                   config.get_db_password(),
                                   source=config.get_auth_db_name())
    conn.drop_database(DATABASE_NAME)

def _import_file(f, dao):
    scraper = TioScraper.from_file(f[0], f[1])
    _import_players(scraper, dao)
    pending_tournament = PendingTournament.from_scraper('tio', scraper, [dao.region])
    pending_tournament.alias_mappings = alias_service.get_alias_mappings(dao, pending_tournament.aliases)
    tournament = Tournament.from_pending_tournament(pending_tournament)
    tournament.save()

def _import_players(scraper, dao):
    for player in scraper.get_players():
        db_player = dao.get_player_by_alias(player)
        if db_player is None:
            db_player = Player(
                    name=player,
                    aliases=[player.lower()],
                    ratings=[Rating.from_trueskill(dao.region, trueskill.Rating())],
                    regions=[dao.region])
            db_player.save()

class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        connect_test_db()

        norcal = Region(id='norcal', display_name='Norcal')
        texas = Region(id='texas', display_name='Texas')
        norcal.save()
        texas.save()

        norcal_dao = Dao('norcal')
        texas_dao = Dao('texas')

        for f in NORCAL_FILES:
            _import_file(f, norcal_dao)

        for f in TEXAS_FILES:
            _import_file(f, texas_dao)

        for f in NORCAL_PENDING_FILES:
            scraper = TioScraper.from_file(f[0], f[1])
            pending_tournament = PendingTournament.from_scraper('tio', scraper, [norcal_dao.region])
            pending_tournament.save()

        now = datetime(2014, 11, 1)
        rankings.generate_ranking(norcal_dao, now=now)
        rankings.generate_ranking(texas_dao, now=now)

        salt, hashed_password = dao.gen_password('rip')
        gar = User(username='gar',
                   salt=salt,
                   hashed_password=hashed_password,
                   admin_regions=[norcal])
        gar.save()

        username = 'asdf'
        user_admin_regions = [norcal]
        user = User(username=username,
                    salt='',
                    hashed_password='',
                    admin_regions=user_admin_regions)
        user.save()

        config = Config(CONFIG_LOCATION)
        subprocess.check_call(['mongodump',
                        '--quiet',
                        '-d', DATABASE_NAME,
                        '-u', config.get_db_user(),
                        '-p', config.get_db_password(),
                        '--authenticationDatabase', config.get_auth_db_name(),
                        '--out', DATABASE_DUMP_FILE])

    def setUp(self):
        connect_test_db()
        # load db from file (faster than reinitializing every time)
        config = Config(CONFIG_LOCATION)
        subprocess.check_call(['mongorestore',
                        '--quiet',
                        '-u', config.get_db_user(),
                        '-p', config.get_db_password(),
                        '--authenticationDatabase', config.get_auth_db_name(),
                        DATABASE_DUMP_FILE])


    #    server.app.config['TESTING'] = True
        self.app = server.app.test_client()
        self.app.testing = True

        # get important objects
        self.norcal = Region.objects.get(id='norcal')
        self.texas = Region.objects.get(id='texas')

        self.norcal_dao = Dao('norcal')
        self.texas_dao = Dao('texas')

        self.username = 'asdf'
        self.user_admin_regions = [self.norcal]
        self.user = User.objects.get(username=self.username)


### start of actual test cases

    def test_cors_checker(self):
        self.assertTrue(server.is_allowed_origin("http://njssbm.com"))
        self.assertTrue(server.is_allowed_origin("https://njssbm.com"))
        self.assertTrue(server.is_allowed_origin("http://njssbm.com:3000"))
        self.assertTrue(server.is_allowed_origin("https://njssbm.com:3000"))
        self.assertTrue(server.is_allowed_origin("http://192.168.33.10"))
        self.assertTrue(server.is_allowed_origin("https://192.168.33.10"))
        self.assertTrue(server.is_allowed_origin("https://192.168.33.10:433"))
        self.assertTrue(server.is_allowed_origin("http://192.168.33.10:433"))
        self.assertTrue(server.is_allowed_origin("http://192.168.33.1"))
        self.assertTrue(server.is_allowed_origin("https://192.168.33.1"))
        self.assertTrue(server.is_allowed_origin("https://192.168.33.1:433"))
        self.assertTrue(server.is_allowed_origin("http://192.168.33.1:433"))
        self.assertTrue(server.is_allowed_origin("http://notgarpr.com:433"))
        self.assertTrue(server.is_allowed_origin("https://notgarpr.com"))
        self.assertTrue(server.is_allowed_origin("https://notgarpr.com:420"))
        self.assertTrue(server.is_allowed_origin("http://notgarpr.com"))
        self.assertTrue(server.is_allowed_origin("http://stage.notgarpr.com"))
        self.assertTrue(server.is_allowed_origin("http://www.notgarpr.com"))
        self.assertTrue(server.is_allowed_origin("https://stage.notgarpr.com"))
        self.assertTrue(server.is_allowed_origin("https://www.notgarpr.com"))
        self.assertTrue(server.is_allowed_origin("http://stage.notgarpr.com:44"))
        self.assertTrue(server.is_allowed_origin("http://www.notgarpr.com:919"))
        self.assertFalse(server.is_allowed_origin("http://garpr.com"))
        self.assertFalse(server.is_allowed_origin("http://notgarpr.com.evil.com"))
        self.assertFalse(server.is_allowed_origin("http://192.168.33.1.evil.com"))
        self.assertFalse(server.is_allowed_origin("http://192.168.33.1:445.evil.com"))
        self.assertFalse(server.is_allowed_origin("http://notgarpr.com:445.evil.com"))
        self.assertFalse(server.is_allowed_origin("http://notgarpr.com:443\x00.evil.com"))
        self.assertFalse(server.is_allowed_origin("http://notgarpr.com:443\r\n.evil.com"))
        self.assertFalse(server.is_allowed_origin("http://notgarpr.com:443\n.evil.com"))

    def test_get_region_list(self):
        data = self.app.get('/regions').data

        expected_region_dict = {
                'regions': [
                    {'id': 'norcal', 'display_name': 'Norcal'},
                    {'id': 'texas', 'display_name': 'Texas'}
                ]
        }

        self.assertEqual(json.loads(data), expected_region_dict)

    def test_get_player_list(self):
        def for_region(json_data, dao):
            self.assertEqual(json_data.keys(), ['players'])
            players_list = json_data['players']
            players_from_db = dao.get_all_players()
            self.assertEqual(len(players_list), len(players_from_db))

            for player in players_list:
                expected_keys = set(['id', 'name', 'merged', 'merge_children', 'merge_parent', 'regions', 'aliases', 'ratings'])
                self.assertTrue(set(player.keys()) < expected_keys)
                self.assertEqual(ObjectId(player['id']), dao.get_player_by_alias(player['name']).id)

        data = self.app.get('/norcal/players').data
        json_data = json.loads(data)
        self.assertEqual(len(json_data['players']), 65)
        for_region(json_data, self.norcal_dao)

        data = self.app.get('/texas/players').data
        json_data = json.loads(data)
        self.assertEqual(len(json_data['players']), 41)
        for_region(json_data, self.texas_dao)

    def test_get_player_list_with_alias(self):
        player = self.norcal_dao.get_player_by_alias('gar')

        data = self.app.get('/norcal/players?alias=gar').data
        json_data = json.loads(data)
        self.assertEqual(len(json_data['players']), 1)

        json_player = json_data['players'][0]
        expected_keys = set(['id', 'name', 'merged', 'merge_children', 'merge_parent', 'regions', 'aliases', 'ratings'])
        self.assertTrue(set(json_player.keys()) < expected_keys)
        self.assertEqual(ObjectId(json_player['id']), player.id)

    def test_get_player_list_case_insensitive(self):
        player = self.norcal_dao.get_player_by_alias('gar')

        data = self.app.get('/norcal/players?alias=GAR').data
        json_data = json.loads(data)
        self.assertEqual(len(json_data['players']), 1)

        json_player = json_data['players'][0]
        expected_keys = set(['id', 'name', 'merged', 'merge_children', 'merge_parent', 'regions', 'aliases', 'ratings'])
        self.assertTrue(set(json_player.keys()) < expected_keys)
        self.assertEqual(ObjectId(json_player['id']), player.id)

    def test_get_player_list_with_bad_alias(self):
        data = self.app.get('/norcal/players?alias=BADALIAS').data
        json_data = json.loads(data)
        self.assertEqual(len(json_data['players']), 0)

    def test_get_player(self):
        player = self.norcal_dao.get_player_by_alias('gar')
        data = self.app.get('/norcal/players/' + str(player.id)).data
        json_data = json.loads(data)

        self.assertEqual(len(json_data.keys()), 7)
        self.assertEqual(json_data['id'], str(player.id))
        self.assertEqual(json_data['name'], 'gar')
        self.assertEqual(json_data['aliases'], ['gar'])
        self.assertEqual(json_data['regions'], ['norcal'])
        self.assertEqual(json_data['ratings'][0]['region'], 'norcal')
        self.assertTrue(json_data['ratings'][0]['mu'] > 0)
        self.assertTrue(json_data['ratings'][0]['sigma'] > 0)
        self.assertEqual(json_data['merged'], False)

        player = self.texas_dao.get_player_by_alias('wobbles')
        data = self.app.get('/texas/players/' + str(player.id)).data
        json_data = json.loads(data)

        print json_data
        self.assertEqual(len(json_data.keys()), 7)
        self.assertEqual(json_data['id'], str(player.id))
        self.assertEqual(json_data['name'], 'Wobbles')
        self.assertEqual(json_data['aliases'], ['wobbles'])
        self.assertEqual(json_data['ratings'][0]['region'], 'texas')
        self.assertTrue(json_data['ratings'][0]['mu'] > 0)
        self.assertTrue(json_data['ratings'][0]['sigma'] > 0)
        self.assertEqual(json_data['merged'], False)

    def test_get_tournament_list(self):
        def for_region(data, dao):
            json_data = json.loads(data)

            self.assertEqual(json_data.keys(), ['tournaments'])
            tournaments_list = json_data['tournaments']
            print tournaments_list
            tournaments_from_db = dao.get_all_tournaments(regions=[dao.region])
            self.assertEqual(len(tournaments_list), len(tournaments_from_db))

            for tournament in tournaments_list:
                tournament_from_db = dao.get_tournament_by_id(ObjectId(tournament['id']))
                self.assertEqual(tournament['id'], str(tournament_from_db.id))
                self.assertEqual(tournament['name'], tournament_from_db.name)
                self.assertEqual(tournament['date'], tournament_from_db.date.strftime('%x'))
                self.assertEqual(tournament['regions'], [dao.region.id])

        data = self.app.get('/norcal/tournaments').data
        for_region(data, self.norcal_dao)

        data = self.app.get('/texas/tournaments').data
        for_region(data, self.texas_dao)

    @patch('server.auth_user')
    def test_get_tournament_list_include_pending(self, mock_auth_user):
        dao = self.norcal_dao
        mock_auth_user.return_value = self.user

        data = self.app.get('/norcal/tournaments?includePending=true').data
        json_data = json.loads(data)

        self.assertEqual(json_data.keys(), ['tournaments', 'pending_tournaments'])
        tournaments_list = json_data['tournaments']
        pending_tournaments_list = json_data['pending_tournaments']
        tournaments_from_db = dao.get_all_tournaments(regions=[dao.region])
        pending_tournaments_from_db = dao.get_all_pending_tournaments(regions=[dao.region])
        self.assertEqual(len(tournaments_list), len(tournaments_from_db))
        self.assertEqual(len(pending_tournaments_list), len(pending_tournaments_from_db))

        for tournament in tournaments_list:
            tournament_from_db = dao.get_tournament_by_id(ObjectId(tournament['id']))
            self.assertEqual(tournament['id'], str(tournament_from_db.id))
            self.assertEqual(tournament['name'], tournament_from_db.name)
            self.assertEqual(tournament['date'], tournament_from_db.date.strftime('%x'))
            self.assertEqual(tournament['regions'], [dao.region.id])

        for pending_tournament in pending_tournaments_list:
            pending_tournament_from_db = dao.get_pending_tournament_by_id(ObjectId(pending_tournament['id']))

            self.assertEqual(pending_tournament['id'], str(pending_tournament_from_db.id))
            self.assertEqual(pending_tournament['name'], pending_tournament_from_db.name)
            self.assertEqual(pending_tournament['date'], pending_tournament_from_db.date.strftime('%x'))
            self.assertEqual(pending_tournament['regions'], [dao.region.id])

    @patch('server.auth_user')
    def test_get_tournament_list_include_pending_false(self, mock_auth_user):
        dao = self.norcal_dao
        mock_auth_user.return_value = self.user

        data = self.app.get('/norcal/tournaments?includePending=false').data
        json_data = json.loads(data)

        self.assertEqual(json_data.keys(), ['tournaments'])
        tournaments_list = json_data['tournaments']
        tournaments_from_db = dao.get_all_tournaments(regions=[dao.region])
        self.assertEqual(len(tournaments_list), len(tournaments_from_db))

        for tournament in tournaments_list:
            tournament_from_db = dao.get_tournament_by_id(ObjectId(tournament['id']))
            self.assertEqual(tournament['id'], str(tournament_from_db.id))
            self.assertEqual(tournament['name'], tournament_from_db.name)
            self.assertEqual(tournament['date'], tournament_from_db.date.strftime('%x'))
            self.assertEqual(tournament['regions'], [dao.region.id])

    # TODO: make new test for this
    # @patch('server.auth_user')
    # def test_get_tournament_list_include_pending_not_logged_in(self, mock_auth_user):
    #     dao = self.norcal_dao
    #     mock_auth_user.return_value = None
    #
    #     data = self.app.get('/norcal/tournaments?includePending=true').data
    #     json_data = json.loads(data)
    #
    #     self.assertEqual(json_data.keys(), ['tournaments'])
    #     tournaments_list = json_data['tournaments']
    #     tournaments_from_db = dao.get_all_tournaments(regions=[dao.region_id])
    #     self.assertEqual(len(tournaments_list), len(tournaments_from_db))
    #
    #     for tournament in tournaments_list:
    #         tournament_from_db = dao.get_tournament_by_id(ObjectId(tournament['id']))
    #         expected_keys = set(['id', 'name', 'date', 'regions'])
    #         self.assertEqual(set(tournament.keys()), expected_keys)
    #         self.assertEqual(tournament['id'], str(tournament_from_db.id))
    #         self.assertEqual(tournament['name'], tournament_from_db.name)
    #         self.assertEqual(tournament['date'], tournament_from_db.date.strftime('%x'))
    #         self.assertEqual(tournament['regions'], [dao.region_id])

    # @patch('server.auth_user')
    # def test_get_tournament_list_include_pending_not_admin(self, mock_auth_user):
    #     self.user.admin_regions = []
    #     mock_auth_user.eturn_value = self.user
    #     dao = self.norcal_dao
    #     data = self.app.get('/norcal/tournaments?includePending=true').data
    #     json_data = json.loads(data)
    #
    #     self.assertEqual(json_data.keys(), ['tournaments'])
    #     tournaments_list = json_data['tournaments']
    #     tournaments_from_db = dao.get_all_tournaments(regions=[dao.region_id])
    #     self.assertEqual(len(tournaments_list), len(tournaments_from_db))
    #
    #     for tournament in tournaments_list:
    #         tournament_from_db = dao.get_tournament_by_id(ObjectId(tournament['id']))
    #         expected_keys = set(['id', 'name', 'date', 'regions'])
    #         self.assertEqual(set(tournament.keys()), expected_keys)
    #         self.assertEqual(tournament['id'], str(tournament_from_db.id))
    #         self.assertEqual(tournament['name'], tournament_from_db.name)
    #         self.assertEqual(tournament['date'], tournament_from_db.date.strftime('%x'))
    #         self.assertEqual(tournament['regions'], [dao.region_id])

    @patch('server.auth_user')
    @patch('server.TioScraper')
    def test_post_to_tournament_list_tio(self, mock_tio_scraper, mock_auth_user):
        mock_auth_user.return_value = self.user
        scraper = TioScraper.from_file(NORCAL_FILES[0][0], NORCAL_FILES[0][1])
        mock_tio_scraper.return_value = scraper
        data = {
            'data': 'data',
            'type': 'tio',
            'bracket': 'bracket'
        }

        response = self.app.post('/norcal/tournaments', data=json.dumps(data), content_type='application/json')
        json_data = json.loads(response.data)

        mock_tio_scraper.assert_called_once_with('data', 'bracket')

        print json_data
        self.assertEqual(1, len(json_data))
        self.assertEqual(24, len(json_data['id']))
        pending_tournament = self.norcal_dao.get_pending_tournament_by_id(ObjectId(json_data['id']))
        self.assertIsNotNone(pending_tournament)
        self.assertEqual(len(pending_tournament.alias_mappings), 59)

    @patch('server.auth_user')
    def test_post_to_tournament_list_tio_missing_bracket(self, mock_auth_user):
        mock_auth_user.return_value = self.user
        data = {
            'data': 'data',
            'type': 'tio',
        }

        response = self.app.post('/norcal/tournaments', data=json.dumps(data), content_type='application/json')

        print response.status_code, response.data
        self.assertEqual(response.status_code, 400)
        self.assertTrue('"Missing bracket name"' in response.data)

    @patch('server.auth_user')
    @patch('server.ChallongeScraper')
    def test_post_to_tournament_list_challonge(self, mock_challonge_scraper, mock_auth_user):
        mock_auth_user.return_value = self.user
        scraper = TioScraper.from_file(NORCAL_FILES[0][0], NORCAL_FILES[0][1])
        mock_challonge_scraper.return_value = scraper
        data = {
            'data': 'data',
            'type': 'challonge'
        }

        response = self.app.post('/norcal/tournaments', data=json.dumps(data), content_type='application/json')
        json_data = json.loads(response.data)

        mock_challonge_scraper.assert_called_once_with('data')

        self.assertEqual(1, len(json_data))
        self.assertEqual(24, len(json_data['id']))
        pending_tournament = self.norcal_dao.get_pending_tournament_by_id(ObjectId(json_data['id']))
        self.assertIsNotNone(pending_tournament)
        self.assertEqual(len(pending_tournament.alias_mappings), 59)

    @patch('server.auth_user')
    def test_post_to_tournament_list_missing_data(self, mock_auth_user):
        mock_auth_user.return_value = self.user
        data = {'type': 'tio'}
        response = self.app.post('/norcal/tournaments', data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertTrue('"data required"' in response.data)

    @patch('server.auth_user')
    def test_post_to_tournament_list_unknown_type(self, mock_auth_user):
        mock_auth_user.return_value = self.user
        data = {
            'data': 'data',
            'type': 'unknown'
        }
        response = self.app.post('/norcal/tournaments', data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertTrue('"Unknown type"' in response.data)

    # @patch('server.auth_user')
    # def test_post_to_tournament_list_invalid_permissions(self, mock_auth_user):
    #     mock_auth_user.return_value = self.user
    #     response = self.app.post('/texas/tournaments')
    #     self.assertEqual(response.status_code, 403)
    #     self.assertEqual('"Permission denied"' in response.data)

    def setup_finalize_tournament_fixtures(self):
        player_1 = Player(
            name='C9 Mango',
            aliases=['C9 Mango'],
            ratings=[Rating.from_trueskill(self.norcal, trueskill.Rating()),
                     Rating.from_trueskill(self.texas, trueskill.Rating())],
            regions=[self.norcal, self.texas])
        player_2 = Player(
            name='[A]rmada',
            aliases=['[A]rmada'],
            ratings=[Rating.from_trueskill(self.norcal, trueskill.Rating()),
                     Rating.from_trueskill(self.texas, trueskill.Rating())],
            regions=[self.norcal, self.texas])
        player_3 = Player(
            name='Liquid`Hungrybox',
            aliases=['Liquid`Hungrybox'],
            ratings=[Rating.from_trueskill(self.norcal, trueskill.Rating())],
            regions=[self.norcal])
        player_4 = Player(
            name='Poor | Zhu',
            aliases=['Poor | Zhu'],
            ratings=[Rating.from_trueskill(self.norcal, trueskill.Rating())],
            regions=[self.norcal])

        players = [player_1, player_2, player_3, player_4]

        player_1_name = 'Mango'
        player_2_name = 'Armada'
        player_3_name = 'Hungrybox'
        player_4_name = 'Zhu'
        new_player_name = 'Scar'

        # pending tournament that can be finalized
        pending_tournament_players_1 = [player_1_name, player_2_name, player_3_name, player_4_name, new_player_name]
        pending_tournament_matches_1 = [
                AliasMatch(winner=player_2_name, loser=player_1_name),
                AliasMatch(winner=player_3_name, loser=player_4_name),
                AliasMatch(winner=player_1_name, loser=player_3_name),
                AliasMatch(winner=player_1_name, loser=player_2_name),
                AliasMatch(winner=player_1_name, loser=player_2_name),
                AliasMatch(winner=player_4_name, loser=new_player_name),
        ]

        pending_tournament_1 = PendingTournament( name='Genesis top 5',
                                                  source_type='tio',
                                                  date=datetime(2009, 7, 10),
                                                  regions=[self.norcal],
                                                  raw='raw',
                                                  aliases=pending_tournament_players_1,
                                                  alias_matches=pending_tournament_matches_1)

        pending_tournament_1.set_alias_mapping(player_1_name, player_1)
        pending_tournament_1.set_alias_mapping(player_2_name, player_2)
        pending_tournament_1.set_alias_mapping(player_3_name, player_3)
        pending_tournament_1.set_alias_mapping(player_4_name, player_4)

        # set id mapping to None for a player that doesn't exist
        pending_tournament_1.set_alias_mapping(new_player_name, None)

        # pending tournament in wrong regions
        pending_tournament_players_2 = [player_1_name, player_2_name]
        pending_tournament_matches_2 = [
                AliasMatch(winner=player_2_name, loser=player_1_name),
        ]

        pending_tournament_2 = PendingTournament( name='Fake Texas Tournament',
                                                  source_type='tio',
                                                  date=datetime(2014, 7, 10),
                                                  raw='raw',
                                                  regions=[self.texas],
                                                  aliases=pending_tournament_players_2,
                                                  alias_matches=pending_tournament_matches_2)

        pending_tournament_2.set_alias_mapping(player_1_name, player_1)
        pending_tournament_2.set_alias_mapping(player_2_name, player_2)

        # incompletely mapped pending tournament
        pending_tournament_3 = PendingTournament( name='Genesis top 4 incomplete',
                                                  source_type='tio',
                                                  date=datetime(2009, 7, 10),
                                                  regions=[self.norcal],
                                                  raw='raw',
                                                  aliases=pending_tournament_players_1,
                                                  alias_matches=pending_tournament_matches_1)

        pending_tournament_3.set_alias_mapping(player_1_name, player_1)
        pending_tournament_3.set_alias_mapping(player_2_name, player_2)
        # Note that Hungrybox and Zhu are unmapped

        for player in players:
            player.save()

        pending_tournament_1.save()
        pending_tournament_3.save()
        pending_tournament_2.save()

        # return players and pending tournaments for test use and cleanup
        # pending tournaments are padded by 0 so indices work out nicely
        return {
            "players": players,
            "pending_tournaments": (0, pending_tournament_1, pending_tournament_2, pending_tournament_3)
        }

    def cleanup_finalize_tournament_fixtures(self, fixtures):
        for player in fixtures["players"]:
            player.delete()
        new_player = self.norcal_dao.get_player_by_alias('Scar')
        if new_player:
            new_player.delete()
        tmp, pending_tournament_1, pending_tournament_2, pending_tournament_3 = fixtures["pending_tournaments"]

        pending_tournament_1.delete()
        pending_tournament_2.delete()
        pending_tournament_3.delete()

    @patch('server.auth_user')
    def test_finalize_nonexistent_tournament(self, mock_auth_user):
        fixtures = self.setup_finalize_tournament_fixtures()
        mock_auth_user.return_value = self.user

        # no pending tournament with this id
        missing_response = self.app.post('/norcal/tournaments/' + str(ObjectId()) + '/finalize')
        self.assertEqual(missing_response.status_code, 400, msg=str(missing_response.data))
        self.assertTrue('"No pending tournament found with that id."' in missing_response.data)

        self.cleanup_finalize_tournament_fixtures(fixtures)

    @patch('server.auth_user')
    def test_finalize_incompletely_mapped_tournament(self, mock_auth_user):
        mock_auth_user.return_value = self.user
        fixtures = self.setup_finalize_tournament_fixtures()
        fixture_pending_tournaments = fixtures["pending_tournaments"]

        # alias_to_id_map doesn't map each alias
        incomplete_response = self.app.post(
            '/norcal/tournaments/' + str(fixture_pending_tournaments[3].id) + '/finalize')
        self.assertEqual(incomplete_response.status_code, 400, msg=str(incomplete_response.data))
        self.assertTrue(
            '"Not all player aliases in this pending tournament have been mapped to player ids."' in incomplete_response.data)

        self.cleanup_finalize_tournament_fixtures(fixtures)

    @patch('server.auth_user')
    def test_finalize_tournament(self, mock_auth_user):
        fixtures = self.setup_finalize_tournament_fixtures()
        fixture_pending_tournaments = fixtures["pending_tournaments"]
        mock_auth_user.return_value = self.user

        # finalize first pending tournament
        success_response = self.app.post(
            '/norcal/tournaments/' + str(fixture_pending_tournaments[1].id) + '/finalize')
        self.assertEqual(success_response.status_code, 200, msg=success_response.data)
        success_response_data = json.loads(success_response.data)
        self.assertTrue(success_response_data['success'])
        self.assertTrue('tournament_id' in success_response_data)
        new_tournament_id = success_response_data['tournament_id']


        # check final list of tournaments
        tournaments_list_response = self.app.get('/norcal/tournaments?includePending=false')
        self.assertEqual(tournaments_list_response.status_code, 200)
        tournaments_data = json.loads(tournaments_list_response.data)
        tournaments_ids = set([str(tournament['id']) for tournament in tournaments_data['tournaments']])
        self.assertTrue(str(new_tournament_id) in tournaments_ids)
        self.assertFalse(str(fixture_pending_tournaments[3].id) in tournaments_ids)

        pending_tournaments_list_response = self.app.get('/norcal/tournaments?includePending=true')
        self.assertEqual(pending_tournaments_list_response.status_code, 200)
        pending_tournaments_data = json.loads(pending_tournaments_list_response.data)
        pending_tournaments_ids = set([str(tournament['id']) for tournament in pending_tournaments_data['tournaments']])

        self.assertTrue(str(new_tournament_id) in pending_tournaments_ids)

        new_player_name = 'Scar'
        new_player = self.norcal_dao.get_player_by_alias(new_player_name)
        self.assertIsNotNone(new_player)
        self.assertEqual(new_player.name, new_player_name)

        self.cleanup_finalize_tournament_fixtures(fixtures)

    def test_get_tournament(self):
        tournament = self.norcal_dao.get_all_tournaments(regions=[self.norcal])[0]
        data = self.app.get('/norcal/tournaments/' + str(tournament.id)).data
        json_data = json.loads(data)

        self.assertEqual(len(json_data.keys()), 4)
        self.assertFalse(json_data['is_pending'])
        self.assertEqual(json_data['tournament']['id'], str(tournament.id))
        self.assertEqual(json_data['tournament']['name'], 'BAM: 4 stocks is not a lead')
        self.assertEqual(json_data['tournament']['source_type'], 'tio')
        self.assertEqual(json_data['tournament']['date'], tournament.date.strftime('%x'))
        self.assertEqual(json_data['tournament']['regions'], ['norcal'])
        self.assertEqual(len(json_data['players']), len(tournament.players))
        self.assertEqual(len(json_data['matches']), len(tournament.matches))

        for player in json_data['players']:
            db_player = self.norcal_dao.get_player_by_id(ObjectId(player['id']))
            self.assertEqual(len(player.keys()), 2)
            self.assertEqual(player['id'], str(db_player.id))
            self.assertEqual(player['name'], db_player.name)

        # spot check first and last match
        match = json_data['matches'][0]
        db_match = tournament.matches[0]
        self.assertEqual(len(match.keys()), 4)
        self.assertEqual(match['winner_id'], str(db_match.winner.id))
        self.assertEqual(match['winner_name'], db_match.winner.name)
        self.assertEqual(match['loser_id'], str(db_match.loser.id))
        self.assertEqual(match['loser_name'], db_match.loser.name)
        match = json_data['matches'][-1]
        db_match = tournament.matches[-1]
        self.assertEqual(len(match.keys()), 4)
        self.assertEqual(match['winner_id'], str(db_match.winner.id))
        self.assertEqual(match['winner_name'], db_match.winner.name)
        self.assertEqual(match['loser_id'], str(db_match.loser.id))
        self.assertEqual(match['loser_name'], db_match.loser.name)

        # sanity tests for another region
        tournament = self.texas_dao.get_all_tournaments()[0]
        data = self.app.get('/texas/tournaments/' + str(tournament.id)).data
        json_data = json.loads(data)

        self.assertEqual(len(json_data.keys()), 4)
        self.assertEqual(json_data['tournament']['id'], str(tournament.id))
        self.assertEqual(json_data['tournament']['name'], 'FX Biweekly 6')
        self.assertEqual(json_data['tournament']['source_type'], 'tio')
        self.assertEqual(json_data['tournament']['date'], tournament.date.strftime('%x'))
        self.assertEqual(json_data['tournament']['regions'], ['texas'])
        self.assertEqual(len(json_data['players']), len(tournament.players))
        self.assertEqual(len(json_data['matches']), len(tournament.matches))

    @patch('server.auth_user')
    def test_get_tournament_pending(self,mock_auth_user):
        mock_auth_user.return_value = self.user
        pending_tournament = self.norcal_dao.get_all_pending_tournaments(regions=[self.norcal])[0]
        data = self.app.get('/norcal/tournaments/' + str(pending_tournament.id)).data
        json_data = json.loads(data)

        self.assertEqual(len(json_data.keys()), 2)
        self.assertEqual(json_data['tournament']['id'], str(pending_tournament.id))
        self.assertEqual(json_data['tournament']['name'], 'bam 6 - 11-8-14')
        self.assertEqual(json_data['tournament']['source_type'], 'tio')
        self.assertEqual(json_data['tournament']['date'], pending_tournament.date.strftime('%x'))
        self.assertEqual(json_data['tournament']['regions'], ['norcal'])
        self.assertEqual(len(json_data['tournament']['aliases']), len(pending_tournament.aliases))
        self.assertEqual(len(json_data['tournament']['alias_matches']), len(pending_tournament.alias_matches))
        self.assertTrue(json_data['is_pending'])

        # spot check 1 match
        match = json_data['tournament']['alias_matches'][0]
        self.assertEqual(len(match.keys()), 2)

    def test_get_tournament_pending_unauth(self):
        pending_tournament = self.norcal_dao.get_all_pending_tournaments(regions=[self.norcal])[0]
        data = self.app.get('/norcal/tournaments/' + str(pending_tournament.id)).data
        print data
        self.assertTrue('"Permission denied"' in data)

    @patch('server.auth_user')
    def test_put_alias_mapping(self, mock_auth_user):
        mock_auth_user.return_value = self.user
        pending_tournament = self.norcal_dao.get_all_pending_tournaments(regions=[self.norcal])[0]
        self.assertEqual(pending_tournament.regions, [self.norcal])

        player_tag = pending_tournament.aliases[0]
        real_player = self.norcal_dao.get_all_players()[0]
        mapping = AliasMapping(player_alias=player_tag, player=real_player)
        self.assertFalse(mapping in pending_tournament.alias_mappings)

        request_data = {'alias_mappings': [{'player_alias': player_tag,
                                            'player_id': str(real_player.id)}]}

        response = self.app.put('/norcal/pending_tournaments/' + str(pending_tournament.id),
            data=json.dumps(request_data), content_type='application/json')
        json_data = json.loads(response.data)
        print json_data

        self.assertEqual(str(pending_tournament.id), json_data['tournament']['id'])

        pending_tournament_from_db = self.norcal_dao.get_pending_tournament_by_id(ObjectId(json_data['tournament']['id']))
        self.assertIsNotNone(pending_tournament)
        self.assertTrue(mapping in pending_tournament_from_db.alias_mappings)

    def test_get_rankings(self):
        data = self.app.get('/norcal/rankings').data
        json_data = json.loads(data)
        db_ranking = self.norcal_dao.get_latest_ranking()

        print json_data
        self.assertEqual(len(json_data.keys()), 2)
        self.assertEqual(json_data['ranking']['time'], db_ranking.time.strftime("%x"))
        self.assertEqual(json_data['ranking']['tournaments'], [str(t.id) for t in db_ranking.tournaments])
        self.assertEqual(json_data['ranking']['region'], self.norcal_dao.region.id)
        self.assertEqual(len(json_data['ranking']['rankings']), len(db_ranking.rankings))

        # spot check first and last ranking entries
        ranking_entry = json_data['ranking_entries'][0]
        db_ranking_entry = db_ranking.rankings[0]
        self.assertEqual(len(ranking_entry.keys()), 4)
        self.assertEqual(ranking_entry['rank'], db_ranking_entry.rank)
        self.assertEqual(ranking_entry['player_id'], str(db_ranking_entry.player.id))
        self.assertEqual(ranking_entry['name'], db_ranking_entry.player.name)
        self.assertTrue(ranking_entry['rating']['mu']>0)
        self.assertTrue(ranking_entry['rating']['sigma']>0)
        ranking_entry = json_data['ranking_entries'][-1]
        db_ranking_entry = db_ranking.rankings[-1]
        self.assertEqual(len(ranking_entry.keys()), 4)
        self.assertEqual(ranking_entry['rank'], db_ranking_entry.rank)
        self.assertEqual(ranking_entry['player_id'], str(db_ranking_entry.player.id))
        self.assertEqual(ranking_entry['name'], db_ranking_entry.player.name)
        self.assertTrue(ranking_entry['rating']['mu'] > -10)

    # TODO: add a safe way to delete players
    # def test_get_rankings_ignore_invalid_player_id(self):
    #     # delete a player that exists in the rankings
    #     db_ranking = self.norcal_dao.get_latest_ranking()
    #     player_to_delete = db_ranking.rankings[1].player
    #     player_to_delete.delete()
    #
    #     data = self.app.get('/norcal/rankings').data
    #     json_data = json.loads(data)
    #     print json_data
    #     db_ranking = self.norcal_dao.get_latest_ranking()
    #
    #     self.assertEqual(len(json_data.keys()), 2)
    #     self.assertEqual(json_data['ranking']['time'], db_ranking.time.strftime("%x"))
    #     self.assertEqual(json_data['ranking']['tournaments'], [str(t.id) for t in db_ranking.tournaments])
    #     self.assertEqual(json_data['ranking']['region'], self.norcal_dao.region.id)
    #
    #     # subtract 1 for the player we removed
    #     self.assertEqual(len(json_data['ranking']), len(db_ranking.ranking) - 1)
    #
    #     # spot check first and last ranking entries
    #     ranking_entry = json_data['ranking'][0]
    #     db_ranking_entry = db_ranking.rankings[0]
    #     self.assertEqual(len(ranking_entry.keys()), 4)
    #     self.assertEqual(ranking_entry['rank'], db_ranking_entry.rank)
    #     self.assertEqual(ranking_entry['id'], str(db_ranking_entry.player))
    #     self.assertEqual(ranking_entry['name'], self.norcal_dao.get_player_by_id(db_ranking_entry.player).name)
    #     self.assertTrue(ranking_entry['rating'] > 24.3)
    #
    #     ranking_entry = json_data['ranking'][-1]
    #     db_ranking_entry = db_ranking.ranking[-1]
    #     self.assertEqual(len(ranking_entry.keys()), 4)
    #     self.assertEqual(ranking_entry['rank'], db_ranking_entry.rank)
    #     self.assertEqual(ranking_entry['id'], str(db_ranking_entry.player))
    #     self.assertEqual(ranking_entry['name'], self.norcal_dao.get_player_by_id(db_ranking_entry.player).name)
    #     self.assertTrue(ranking_entry['rating'] > -3.86)

    @patch('server.auth_user')
    def test_post_rankings(self, mock_auth_user):
        mock_auth_user.return_value = self.user

        data = self.app.post('/norcal/rankings').data
        json_data = json.loads(data)
        db_ranking = self.norcal_dao.get_latest_ranking()

        print json_data
        self.assertEqual(json_data['ranking']['time'], db_ranking.time.strftime("%x"))
        self.assertEqual(len(json_data['ranking']['rankings']), len(db_ranking.rankings))

    # @patch('server.auth_user')
    # def test_post_rankings_permission_denied(self, mock_auth_user):
    #     mock_auth_user.return_value = self.user
    #
    #     response = self.app.post('/texas/rankings')
    #     self.assertEqual(response.status_code, 403)
    #     self.assertEqual(response.data, '"Permission denied"')

    def test_get_matches(self):
        player = self.norcal_dao.get_player_by_alias('gar')
        data = self.app.get('/norcal/matches/' + str(player.id)).data
        json_data = json.loads(data)

        self.assertEqual(len(json_data.keys()), 4)
        self.assertEqual(json_data['player']['id'], str(player.id))
        self.assertEqual(json_data['player']['name'], player.name)
        self.assertEqual(json_data['wins'], 3)
        self.assertEqual(json_data['losses'], 4)

        matches = json_data['matches']
        self.assertEqual(len(matches), 7)

        # spot check a few matches
        match = matches[0]
        opponent = self.norcal_dao.get_player_by_alias('darrell')
        tournament = self.norcal_dao.get_all_tournaments(regions=[self.norcal])[0]
        self.assertEqual(len(match.keys()), 6)
        self.assertEqual(match['opponent_id'], str(opponent.id))
        self.assertEqual(match['opponent_name'], opponent.name)
        self.assertEqual(match['result'], 'lose')
        self.assertEqual(match['tournament_id'], str(tournament.id))
        self.assertEqual(match['tournament_name'], tournament.name)
        self.assertEqual(match['tournament_date'], tournament.date.strftime("%x"))

        match = matches[2]
        opponent = self.norcal_dao.get_player_by_alias('eric')
        tournament = self.norcal_dao.get_all_tournaments(regions=[self.norcal])[1]
        self.assertEqual(len(match.keys()), 6)
        self.assertEqual(match['opponent_id'], str(opponent.id))
        self.assertEqual(match['opponent_name'], opponent.name)
        self.assertEqual(match['result'], 'win')
        self.assertEqual(match['tournament_id'], str(tournament.id))
        self.assertEqual(match['tournament_name'], tournament.name)
        self.assertEqual(match['tournament_date'], tournament.date.strftime("%x"))

    def test_get_matches_with_opponent(self):
        player = self.norcal_dao.get_player_by_alias('gar')
        opponent = self.norcal_dao.get_player_by_alias('tang')
        data = self.app.get('/norcal/matches/' + str(player.id) + "?opponent=" + str(opponent.id)).data
        json_data = json.loads(data)

        self.assertEqual(len(json_data.keys()), 5)
        self.assertEqual(json_data['wins'], 0)
        self.assertEqual(json_data['losses'], 1)

        self.assertEqual(json_data['player']['id'], str(player.id))
        self.assertEqual(json_data['player']['name'], player.name)

        self.assertEqual(json_data['opponent']['id'], str(opponent.id))
        self.assertEqual(json_data['opponent']['name'], opponent.name)

        matches = json_data['matches']
        self.assertEqual(len(matches), 1)

        match = matches[0]
        tournament = self.norcal_dao.get_all_tournaments(regions=[self.norcal])[0]
        self.assertEqual(len(match.keys()), 6)
        self.assertEqual(match['opponent_id'], str(opponent.id))
        self.assertEqual(match['opponent_name'], opponent.name)
        self.assertEqual(match['result'], 'lose')
        self.assertEqual(match['tournament_id'], str(tournament.id))
        self.assertEqual(match['tournament_name'], tournament.name)
        self.assertEqual(match['tournament_date'], tournament.date.strftime("%x"))

    @patch('server.auth_user')
    def test_get_current_user(self, mock_auth_user):
        mock_auth_user.return_value = self.user
        data = self.app.get('/users/session').data
        json_data = json.loads(data)
        print json_data
        self.assertEqual(json_data['id'], self.username)

    @patch('server.auth_user')
    def test_put_tournament_name_change(self, mock_auth_user):
        #initial setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        #pick a tournament
        tournaments_from_db = dao.get_all_tournaments(regions=[self.norcal])
        the_tourney = dao.get_tournament_by_id(tournaments_from_db[0].id)

        #save info about it
        tourney_id = the_tourney.id
        old_date = the_tourney.date
        old_matches = the_tourney.matches
        old_players = the_tourney.players
        old_raw = the_tourney.raw
        old_regions = the_tourney.regions
        old_type = the_tourney.source_type

        #construct info for first test
        new_tourney_name = "jessesGodlikeTourney"
        raw_dict = {'name': new_tourney_name}
        test_data = json.dumps(raw_dict)

        #try overwriting an existing tournament and changing just its name, make sure all the other attributes are fine
        rv = self.app.put('/norcal/tournaments/' + str(tourney_id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '200 OK')
        the_tourney = dao.get_tournament_by_id(tourney_id)
        self.assertEqual(the_tourney.name, new_tourney_name, msg=rv.data)
        self.assertEqual(old_date, the_tourney.date)
        self.assertEqual(old_matches, the_tourney.matches)
        self.assertEqual(old_players, the_tourney.players)
        self.assertEqual(old_raw, the_tourney.raw)
        self.assertEqual(old_regions, the_tourney.regions)
        self.assertEqual(old_type, the_tourney.source_type)

    @patch('server.auth_user')
    def test_put_tournament_everything_change(self, mock_auth_user):
        #initial setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        #pick a tournament
        tournaments_from_db = dao.get_all_tournaments(regions=[self.norcal])
        the_tourney = dao.get_tournament_by_id(tournaments_from_db[0].id)

        #save info about it
        tourney_id = the_tourney.id
        new_tourney_name = "jessesGodlikeTourney"
        old_raw = the_tourney.raw
        old_type = the_tourney.source_type
        #setup for test 2
        player1 = Player(name='testshroomed',
                         aliases=['testshroomed'],
                         ratings=[Rating.from_trueskill(self.norcal, trueskill.Rating())],
                         regions=[self.norcal])
        player2 = Player(name='testpewpewu',
                         aliases=['testpewpewu'],
                         ratings=[Rating.from_trueskill(self.norcal, trueskill.Rating())],
                         regions=[self.norcal])
        player1.save()
        player2.save()

        new_players = (player1, player2)
        new_matches = (Match(winner=player1, loser=player2), Match(winner=player2, loser=player1))

        new_matches_for_wire = ({'winner': str(player1.id), 'loser': str(player2.id) }, {'winner': str(player2.id), 'loser': str(player1.id)})
        new_date = datetime.now()
        new_regions = ["norcal"]
        raw_dict = {'name': new_tourney_name, 'date': new_date.strftime("%m/%d/%y"), 'matches': new_matches_for_wire, 'regions': new_regions, 'players': [str(p.id) for p in new_players]}
        test_data = json.dumps(raw_dict)

        # try overwriting all its writeable attributes: date players matches regions
        rv = self.app.put('/norcal/tournaments/' + str(tourney_id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '200 OK')
        json_data = json.loads(rv.data)
        print json_data

        # check that things are correct
        self.assertEqual(json_data['tournament']['name'], new_tourney_name)
        self.assertEqual(json_data['tournament']['date'], new_date.strftime('%m/%d/%y'))
        for m1, m2 in zip(json_data['tournament']['matches'], new_matches):
            self.assertEqual(m1['winner'], str(m2.winner.id))
            self.assertEqual(m1['loser'], str(m2.loser.id))
        for p1, p2 in zip(json_data['tournament']['players'], new_players):
            self.assertEqual(p1, str(p2.id))
        self.assertEqual(set(json_data['tournament']['regions']), set(new_regions))

        the_tourney = dao.get_tournament_by_id(tourney_id)
        self.assertEqual(new_tourney_name, the_tourney.name)
        self.assertEqual(new_date.toordinal(), the_tourney.date.toordinal())
        for m1, m2 in zip(new_matches, the_tourney.matches):
            self.assertEqual(m1.winner, m2.winner)
            self.assertEqual(m1.loser, m2.loser)

        self.assertEqual(set(new_players), set(the_tourney.players))
        self.assertEqual(old_raw, the_tourney.raw)
        self.assertEqual(set(new_regions), set([r.id for r in the_tourney.regions]))
        self.assertEqual(old_type, the_tourney.source_type)

    @patch('server.auth_user')
    def test_put_tournament_invalid_player_name(self, mock_auth_user):
        #initial setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        #pick a tournament
        tournaments_from_db = dao.get_all_tournaments(regions=[self.norcal])
        the_tourney = tournaments_from_db[0]
        #save info about it
        tourney_id = the_tourney.id
        #non string player name
        raw_dict = {'players': ("abc", 123)}
        test_data = json.dumps(raw_dict)
        rv = self.app.put('/norcal/tournaments/' + str(tourney_id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '400 BAD REQUEST')

    @patch('server.auth_user')
    def test_put_tournament_invalid_winner(self, mock_auth_user):
        #initial setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        #pick a tournament
        tournaments_from_db = dao.get_all_tournaments(regions=[self.norcal])
        the_tourney = tournaments_from_db[0]
        #save info about it
        tourney_id = the_tourney.id
        #match with numerical winner
        raw_dict = {'matches': {'winner': 123, 'loser': 'bob'}}
        test_data = json.dumps(raw_dict)
        rv = self.app.put('/norcal/tournaments/' + str(tourney_id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '400 BAD REQUEST')

    @patch('server.auth_user')
    def test_put_tournament_invalid_types_loser(self, mock_auth_user):
        #initial setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        #pick a tournament
        tournaments_from_db = dao.get_all_tournaments(regions=[self.norcal])
        the_tourney = tournaments_from_db[0]
        #save info about it
        tourney_id = the_tourney.id
        #match with numerical loser
        raw_dict = {'matches': {'winner': 'bob', 'loser': 123}}
        test_data = json.dumps(raw_dict)
        rv = self.app.put('/norcal/tournaments/' + str(tourney_id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '400 BAD REQUEST')

    @patch('server.auth_user')
    def test_put_tournament_invalid_types_both(self, mock_auth_user):
        #initial setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        #pick a tournament
        tournaments_from_db = dao.get_all_tournaments(regions=[self.norcal])
        the_tourney = tournaments_from_db[0]
        #save info about it
        tourney_id = the_tourney.id
        #match with both numerical
        raw_dict = {'matches': {'winner': 1234, 'loser': 123}}
        test_data = json.dumps(raw_dict)
        rv = self.app.put('/norcal/tournaments/' + str(tourney_id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '400 BAD REQUEST')

    @patch('server.auth_user')
    def test_put_tournament_invalid_region(self, mock_auth_user):
        #initial setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        #pick a tournament
        tournaments_from_db = dao.get_all_tournaments(regions=[self.norcal])
        the_tourney = tournaments_from_db[0]
        #save info about it
        tourney_id = the_tourney.id
        #match with both numerical
        raw_dict = {'regions': ("abc", 123)}
        test_data = json.dumps(raw_dict)
        rv = self.app.put('/norcal/tournaments/' + str(tourney_id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '400 BAD REQUEST')

    @patch('server.auth_user')
    def test_put_tournament_invalid_matches(self, mock_auth_user):
        #initial setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        #pick a tournament
        tournaments_from_db = dao.get_all_tournaments(regions=[self.norcal])
        the_tourney = tournaments_from_db[0]
        #save info about it
        tourney_id = the_tourney.id
        #match with both numerical
        raw_dict = {'matches': 123}
        test_data = json.dumps(raw_dict)
        rv = self.app.put('/norcal/tournaments/' + str(tourney_id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '400 BAD REQUEST')

    @patch('server.auth_user')
    def test_put_player_update_name(self, mock_auth_user):
        #setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        players = dao.get_all_players()
        the_player = players[0]
        player_id = the_player.id
        old_regions = the_player.regions
        old_aliases = the_player.aliases
        old_ratings = the_player.ratings

        #construct info for first test
        new_name = 'someone'
        raw_dict = {'name': new_name}
        test_data = json.dumps(raw_dict)

        #test updating name
        rv = self.app.put('/norcal/players/' + str(the_player.id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '200 OK')
        the_player = dao.get_player_by_id(player_id)
        self.assertEqual(the_player.ratings, old_ratings)
        self.assertEqual(set(the_player.aliases), set(old_aliases))
        self.assertEqual(set(the_player.regions), set(old_regions))
        self.assertEqual(the_player.name, new_name)

    @patch('server.auth_user')
    def test_put_player_update_aliases(self, mock_auth_user):
        #setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        players = dao.get_all_players()
        the_player = players[0]
        player_id = the_player.id
        old_regions = the_player.regions
        old_ratings = the_player.ratings

        #first, change their name
        new_name = 'someone'
        raw_dict = {'name': new_name}
        test_data = json.dumps(raw_dict)

        rv = self.app.put('/norcal/players/' + str(the_player.id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '200 OK')

        #construct info for second test
        new_aliases = ('someone', 'someoneelse', 'unknowndude')
        raw_dict = {'aliases': new_aliases}
        test_data = json.dumps(raw_dict)

        #test updating aliases
        rv = self.app.put('/norcal/players/' + str(the_player.id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '200 OK', msg=rv.data)
        the_player = dao.get_player_by_id(player_id)
        self.assertEqual(set(the_player.aliases), set(new_aliases))
        self.assertEqual(the_player.ratings, old_ratings)
        self.assertEqual(set(the_player.regions), set(old_regions))

    @patch('server.auth_user')
    def test_put_player_invalid_aliases(self, mock_auth_user):
        #setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        players = dao.get_all_players()
        the_player = players[0]

        #construct info for third test
        new_aliases = ('nope', 'someoneelse', 'unknowndude')
        raw_dict = {'aliases': new_aliases}
        test_data = json.dumps(raw_dict)

        #test updating aliases with invalid aliases list
        rv = self.app.put('/norcal/players/' + str(the_player.id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '400 BAD REQUEST')

    @patch('server.auth_user')
    def test_put_player_update_regions(self, mock_auth_user):
        #setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        players = dao.get_all_players()
        the_player = players[0]
        player_id = the_player.id
        old_ratings = the_player.ratings

        #construct info for fourth test
        new_regions = ('norcal', 'texas')
        raw_dict = {'regions': new_regions}
        test_data = json.dumps(raw_dict)

        #test updating regions
        rv = self.app.put('/norcal/players/' + str(the_player.id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '200 OK', msg=rv.data)
        the_player = dao.get_player_by_id(player_id)
        self.assertEqual(the_player.ratings, old_ratings)
        self.assertEqual(set([r.id for r in the_player.regions]), set(new_regions))

    @patch('server.auth_user')
    def test_put_player_nonstring_aliases(self, mock_auth_user):
        #setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        players = dao.get_all_players()
        the_player = players[0]
        #construct info for test
        raw_dict = {'aliases': ('abc', 123)}
        test_data = json.dumps(raw_dict)

        #test updating regions
        rv = self.app.put('/norcal/players/' + str(the_player.id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '400 BAD REQUEST')

    @patch('server.auth_user')
    def test_put_player_nonstring_regions(self, mock_auth_user):
        #setup
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        players = dao.get_all_players()
        the_player = players[0]
        player_id = the_player.id
        #construct info for test
        aliases = ('norcal', 'nyc')
        raw_dict = {'aliases': ('abc', 123)}
        test_data = json.dumps(raw_dict)

        #test updating regions
        rv = self.app.put('/norcal/players/' + str(the_player.id), data=test_data, content_type='application/json')
        self.assertEqual(rv.status, '400 BAD REQUEST')

    @patch('server.auth_user')
    def test_put_merge(self, mock_auth_user):
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        all_players = dao.get_all_players()
        player_one = all_players[0]

        # dummy player to merge
        player_two = Player(name='blah',
                            aliases=['blah'],
                            ratings=[],
                            regions=[self.norcal])
        player_two.save()

        raw_dict = {'target_player_id': str(player_one.id), 'source_player_id' : str(player_two.id) }
        test_data = json.dumps(raw_dict)
        rv = self.app.put('/norcal/merges', data=str(test_data), content_type='application/json')
        self.assertEqual(rv.status, '200 OK', msg=rv.data)
        print rv.data, rv.status
        data_dict = json.loads(rv.data)
        merge_id = data_dict['id']
        self.assertTrue(merge_id, msg=merge_id)
        # okay, now look in the dao and see if the merge is actually in there
        the_merge = dao.get_merge(ObjectId(merge_id))
        print merge_id, the_merge
        # assert the correct player is in the correct place
        self.assertTrue(the_merge, msg=merge_id)
        self.assertEqual(the_merge.target_player.id, player_one.id)
        self.assertEqual(the_merge.source_player.id, player_two.id)

    @patch('server.auth_user')
    def test_put_merge_invalid_id(self, mock_auth_user):
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        raw_dict = {'target_player_id': "abcd", 'source_player_id' : "adskj" }
        test_data = json.dumps(raw_dict)
        rv = self.app.put('/norcal/merges', data=str(test_data), content_type='application/json')
        self.assertTrue("\"invalid ids, that wasn't an ObjectID\"" in rv.data)


    @patch('server.auth_user')
    def test_put_merge_target_not_found(self, mock_auth_user):
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        all_players = dao.get_all_players()
        player_one = all_players[0]
        player_two = all_players[1]
        raw_dict = {'target_player_id': "552f53650181b84aaaa01051", 'source_player_id' : str(player_two.id)  }
        test_data = json.dumps(raw_dict)
        rv = self.app.put('/norcal/merges', data=str(test_data), content_type='application/json')
        print rv.data
        self.assertTrue("\"target player not found\"" in rv.data)


    @patch('server.auth_user')
    def test_put_merge_source_not_found(self, mock_auth_user):
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        all_players = dao.get_all_players()
        player_one = all_players[0]
        player_two = all_players[1]
        raw_dict = {'target_player_id': str(player_one.id), 'source_player_id' : "552f53650181b84aaaa01051"  }
        test_data = json.dumps(raw_dict)
        rv = self.app.put('/norcal/merges', data=str(test_data), content_type='application/json')
        self.assertTrue("\"source player not found\"" in rv.data)

    @patch('server.auth_user')
    def test_post_tournament_from_tio(self, mock_auth_user):
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        #print "all regions:", ' '.join( x.id for x in dao.get_all_regions(self.mongo_client))
        raw_dict = {}
        #then try sending a valid tio tournament and see if it works
        with open('test/data/Justice4.tio') as f:
            raw_dict['data'] = f.read()[3:] #weird hack, cause the first 3 bytes of a tio file are unprintable and that breaks something
        raw_dict['type'] = "tio"
        raw_dict['bracket'] = 'Bracket'
        the_data = json.dumps(raw_dict)
        response = self.app.post('/norcal/tournaments', data=the_data, content_type='application/json')
        for x in response.data:
            self.assertTrue(x in string.printable)
        self.assertEqual(response.status_code, 200, msg=str(response.data) + str(response.status_code))
        the_dict = json.loads(response.data)
        the_tourney = dao.get_pending_tournament_by_id(ObjectId(the_dict['id']))

        self.assertEqual(the_tourney.name, u'Justice 4')
        self.assertEqual(len(the_tourney.aliases), 48)

        self.assertEqual(the_dict['id'], str(the_tourney.id))
        self.assertEqual(the_tourney.source_type, 'tio')
        self.assertEqual(the_tourney.regions, [self.norcal])

        #let's spot check and make sure hax vs armada happens twice
        sweden_wins_count = 0
        for m in the_tourney.alias_matches:
            if m.winner == "P4K | EMP | Armada" and m.loser == "VGBC | Hax":
                sweden_wins_count += 1
        self.assertEqual(sweden_wins_count, 2, msg="armada didn't double elim hax??")

    @patch('server.auth_user')
    def test_post_tournament_from_tio_without_trim(self, mock_auth_user): #TODO: rewrite to use new endpoint
        mock_auth_user.return_value = self.user
        dao = self.norcal_dao
        #print "all regions:", ' '.join( x.id for x in dao.get_all_regions(self.mongo_client))
        raw_dict = {}
        #then try sending a valid tio tournament and see if it works
        with open('test/data/Justice4.tio') as f:
            raw_dict['data'] = f.read() #NO TRIM BB
       # raw_dict['tournament_name'] = "Justice4"
        raw_dict['type'] = "tio"
        raw_dict['bracket'] = 'Bracket'
        the_data = json.dumps(raw_dict)
        response = self.app.post('/norcal/tournaments', data=the_data, content_type='application/json')
        self.assertEqual(response.status_code, 503, msg=response.data)

    def test_put_session(self):
        result = User.objects.get(username="gar")
        username = "gar"
        passwd = "rip"
        raw_dict = {}
        raw_dict['username'] = username
        raw_dict['password'] = passwd
        the_data = json.dumps(raw_dict)
        response = self.app.put('/users/session', data=the_data, content_type='application/json')
        self.assertEqual(response.status_code, 200, msg=response.headers)
        self.assertTrue('Set-Cookie' in response.headers.keys(), msg=str(response.headers))
        cookie_string = response.headers['Set-Cookie']
        my_cookie = cookie_string.split('"')[1] #split sessionID out of cookie string
        result = Session.objects.get(id=my_cookie)

    def test_put_session_bad_creds(self):
        username = "gar"
        passwd = "stillworksongarpr"
        raw_dict = {}
        raw_dict['username'] = username
        raw_dict['password'] = passwd
        the_data = json.dumps(raw_dict)
        response = self.app.put('/users/session', data=the_data, content_type='application/json')
        self.assertEqual(response.status_code, 403, msg=response.data)

    def test_put_session_bad_user(self): #this test is to make sure we dont have username enumeration (up to a timing attack anyway)
        username = "evilgar"
        passwd = "stillworksongarpr"
        raw_dict = {}
        raw_dict['username'] = username
        raw_dict['password'] = passwd
        the_data = json.dumps(raw_dict)
        response = self.app.put('/users/session', data=the_data, content_type='application/json')
        self.assertEqual(response.status_code, 403, msg=response.data)

    @patch('server.auth_user')
    def test_delete_finalized_tournament(self, mock_get_user_from_access_token):
        mock_get_user_from_access_token.return_value = self.user
        tournament = self.norcal_dao.get_all_tournaments(regions=[self.norcal])[0]
        response = self.app.delete('/norcal/tournaments/' + str(tournament.id))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.norcal_dao.get_tournament_by_id(tournament.id) is None, msg=self.norcal_dao.get_tournament_by_id(tournament.id))

    @patch('server.auth_user')
    def test_delete_pending_tournament(self, mock_get_user_from_access_token):
        mock_get_user_from_access_token.return_value = self.user
        tournament = self.norcal_dao.get_all_pending_tournaments(regions=[self.norcal])[0]
        response = self.app.delete('/norcal/tournaments/' + str(tournament.id))
        self.assertEqual(response.status_code, 200, msg=response.status_code)
        self.assertTrue(self.norcal_dao.get_pending_tournament_by_id(tournament.id) is None, msg=self.norcal_dao.get_pending_tournament_by_id(tournament.id))

    def test_delete_pending_tournament_unauth(self):
        tournament = self.norcal_dao.get_all_pending_tournaments(regions=[self.norcal])[0]
        response = self.app.delete('/norcal/tournaments/' + str(tournament.id))
        self.assertEqual(response.status_code, 403, msg=response.status_code)

    def test_delete_finalized_tournament_unauth(self):
        tournament = self.norcal_dao.get_all_tournaments(regions=[self.norcal])[0]
        response = self.app.delete('/norcal/tournaments/' + str(tournament.id))
        self.assertEqual(response.status_code, 403)
