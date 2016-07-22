import unittest
import mock
import os
import trueskill

from datetime import datetime
from mongoengine import connect, register_connection
from pymongo import MongoClient

from config.config import Config
from model import *
from scraper.challonge import ChallongeScraper

# mongomock currently has issues with MongoEngine:
# (https://github.com/MongoEngine/mongoengine/issues/1045)
# should switch back to mongomock after resolved
DATABASE_NAME = 'garpr_test'
CONFIG_LOCATION = os.path.abspath(os.path.dirname(__file__) + '/../config/config.ini')

def connect_test_db():
    config = Config(CONFIG_LOCATION)
    conn = connect(DATABASE_NAME)
    conn.the_database.authenticate(config.get_db_user(),
                                   config.get_db_password(),
                                   source=config.get_auth_db_name())
    conn.drop_database(DATABASE_NAME)

# TODO: refactor common initialization code (i.e. initializing players)
#   to their own global routines

class TestAliasMapping:
    pass

class TestAliasMatch:
    pass

class TestMatch(unittest.TestCase):
    def setUp(self):
        connect_test_db()

        self.p1 = Player(name="p1")
        self.p2 = Player(name="p2")
        self.p3 = Player(name="p3")

        self.p1.save()
        self.p2.save()
        self.p3.save()

        self.match1 = Match(winner=self.p1, loser=self.p2)
        self.match2 = Match(winner=self.p1, loser=self.p3)

    def test_to_string(self):
        self.assertEqual(str(self.match1), '%s > %s' % (self.p1, self.p2))

    def test_contains_players(self):
        self.assertTrue(self.match1.contains_players(self.p1.id, self.p2.id))
        self.assertTrue(self.match1.contains_players(self.p2.id, self.p1.id))

        self.assertFalse(self.match1.contains_players(self.p2.id, self.p2.id))
        self.assertFalse(self.match1.contains_players(self.p2.id, self.p3.id))

    def test_did_player_win(self):
        self.assertTrue(self.match1.did_player_win(self.p1.id))
        self.assertFalse(self.match1.did_player_win(self.p2.id))

    def test_get_opposing_player_id(self):
        self.assertEqual(self.match1.get_opposing_player_id(self.p1.id), self.p2.id)
        self.assertEqual(self.match1.get_opposing_player_id(self.p2.id), self.p1.id)
        self.assertIsNone(self.match1.get_opposing_player_id(self.p3.id))

    def test_replace_player(self):
        self.match1.replace_player(self.p2, self.p3)
        self.assertTrue(self.match1.contains_players(self.p1.id, self.p3.id))

        self.match2.replace_player(self.p1, self.p2)
        self.assertTrue(self.match2.contains_players(self.p2.id, self.p3.id))
        self.assertTrue(self.match2.did_player_win(self.p2.id))

class TestRankingEntry(unittest.TestCase):
    pass

class TestRating(unittest.TestCase):
    def setUp(self):
        connect_test_db()

        self.norcal = Region(id='norcal', display_name='Norcal')
        self.rating = Rating(region=self.norcal,
                             mu=0.0,
                             sigma=1.0)

    def test_to_string(self):
        self.assertEqual(str(self.rating), "(mu=0.00,sigma=1.00)")

    def test_from_trueskill(self):
        true_rating1 = trueskill.Rating()
        true_rating2 = trueskill.Rating(mu=5., sigma=1.)

        rating1 = Rating.from_trueskill(self.norcal, true_rating1)
        rating2 = Rating.from_trueskill(self.norcal, true_rating2)

        self.assertEqual(rating1.mu, true_rating1.mu)
        self.assertEqual(rating1.sigma, true_rating1.sigma)

        self.assertEqual(rating2.mu, true_rating2.mu)
        self.assertEqual(rating2.sigma, true_rating2.sigma)

class TestMerge(unittest.TestCase):
    def setUp(self):
        connect_test_db()

        self.p1 = Player(name="p1")
        self.p2 = Player(name="p2")

        self.p1.save()
        self.p2.save()

        self.user = User(username="bob",
                         salt="test",
                         hashed_password="test")
        self.user.save()

        self.merge = Merge(requester=self.user,
                           source_player=self.p1,
                           target_player=self.p2,
                           time=datetime(2016,1,1))

    def test_to_string(self):
        self.assertEqual(str(self.merge),
                          "%s merged into %s" % (self.p1, self.p2))


class TestPlayer(unittest.TestCase):
    def setUp(self):
        connect_test_db()

        self.player_1 = Player(name='gar')
        self.player_1.save()

    def test_clean(self):
        self.assertEqual(len(self.player_1.aliases), 1)
        self.assertEqual(self.player_1.aliases[0], 'gar')

        # check that it lower_cases aliases
        test_player = Player(name='the irish MAFIA')
        test_player.save()
        self.assertEqual(test_player.aliases[0], 'the irish mafia')

        # check we don't add aliases if they already exist
        test_aliases = ['emanon', 'jtp', 'noname']
        test_player = Player(name='Emanon', aliases=test_aliases)
        test_player.save()
        self.assertEqual(test_player.aliases, test_aliases)

    def test_validate_merged(self):
        bad_player = Player(name='garr', merged=True)

        with self.assertRaises(ValidationError) as cm:
            bad_player.save()
        self.assertTrue("player is merged but has no parent" in cm.exception.message)

        bad_player_2 = Player(name='garrr', merge_parent=self.player_1)
        with self.assertRaises(ValidationError) as cm:
            bad_player_2.save()
        self.assertTrue("player has merge_parent but is not merged" in cm.exception.message)

    def test_to_string(self):
        self.assertEqual(
                str(self.player_1),
                "gar (%s)" % str(self.player_1.id))

class TestRegion(unittest.TestCase):
    def setUp(self):
        connect_test_db()

        self.norcal = Region(id='norcal', display_name="Northern California")
        self.norcal.save()

    def test_to_string(self):
        self.assertEqual(str(self.norcal), "Northern California (norcal)")

class TestRanking(unittest.TestCase):
    def setUp(self):
        connect_test_db()

        self.norcal = Region(id='norcal', display_name='Norcal')
        self.texas = Region(id='texas', display_name='Texas')
        self.norcal.save()
        self.texas.save()

        self.player_1 = Player(name='gar')
        self.player_2 = Player(name='sfat')
        self.player_3 = Player(name='shroomed')
        self.player_4 = Player(name='ppu')
        self.player_5 = Player(name='ss')
        self.player_6 = Player(name='hmw')
        self.player_1.save()
        self.player_2.save()
        self.player_3.save()
        self.player_4.save()
        self.player_5.save()
        self.player_6.save()

        self.match_1 = Match(winner=self.player_1, loser=self.player_2)
        self.match_2 = Match(winner=self.player_3, loser=self.player_4)

        self.name = 'tournament'
        self.source_type = 'tio'
        self.date = datetime(2016,1,1)
        self.regions = [self.norcal, self.texas]
        self.raw = 'raw'
        self.players = [self.player_1, self.player_2, self.player_3, self.player_4]
        self.matches = [self.match_1, self.match_2]

        self.tournament = Tournament(
                    name=self.name,
                    source_type=self.source_type,
                    date=self.date,
                    regions=self.regions,
                    raw=self.raw,
                    players=self.players,
                    matches=self.matches)
        self.tournament.save()

        self.ranking_entries = [RankingEntry(rank=1, player=self.player_1),
                                RankingEntry(rank=2, player=self.player_3),
                                RankingEntry(rank=3, player=self.player_2),
                                RankingEntry(rank=4, player=self.player_4)]
        self.ranking = Ranking(region=self.norcal,
                          time=datetime(2016,1,1),
                          rankings=self.ranking_entries,
                          tournaments=[self.tournament])
        self.ranking.save()

    def test_to_string(self):
        ranking_strs = str(self.ranking).split(';')
        self.assertEqual(len(ranking_strs), 4)
        self.assertEqual(ranking_strs[0], '1. gar (%s)' % self.player_1.id)

class TestSession(unittest.TestCase):
    def setUp(self):
        connect_test_db()

        self.norcal = Region(id='norcal', display_name='Norcal')
        self.texas = Region(id='texas', display_name='Texas')
        self.norcal.save()
        self.texas.save()

        self.username = "bob"
        self.salt = "test"
        self.hashed_password = "test"
        self.admin_regions = [self.norcal, self.texas]
        self.user = User(username=self.username,
                         salt=self.salt,
                         hashed_password=self.hashed_password,
                         admin_regions=self.admin_regions)
        self.user.save()

        self.session_id = 'abc123'
        self.session = Session(id=self.session_id,
                               user=self.user)
        self.session.save()

    def test_to_string(self):
        self.assertEqual(str(self.session), 'abc123 (bob)')

class TestTournament(unittest.TestCase):
    def setUp(self):
        connect_test_db()

        self.norcal = Region(id='norcal', display_name='Norcal')
        self.texas = Region(id='texas', display_name='Texas')

        self.norcal.save()
        self.texas.save()

        self.player_1 = Player(name='gar')
        self.player_2 = Player(name='sfat')
        self.player_3 = Player(name='shroomed')
        self.player_4 = Player(name='ppu')
        self.player_5 = Player(name='ss')
        self.player_6 = Player(name='hmw')

        self.player_1.save()
        self.player_2.save()
        self.player_3.save()
        self.player_4.save()
        self.player_5.save()
        self.player_6.save()

        self.match_1 = Match(winner=self.player_1, loser=self.player_2)
        self.match_2 = Match(winner=self.player_3, loser=self.player_4)

        self.name = 'tournament'
        self.source_type = 'tio'
        self.date = datetime(2016,1,1)
        self.regions = [self.norcal, self.texas]
        self.raw = 'raw'
        self.players = [self.player_1, self.player_2, self.player_3, self.player_4]
        self.matches = [self.match_1, self.match_2]

        self.tournament = Tournament(
                    name=self.name,
                    source_type=self.source_type,
                    date=self.date,
                    regions=self.regions,
                    raw=self.raw,
                    players=self.players,
                    matches=self.matches)
        self.tournament.save()

    def test_clean(self):
        self.assertEqual(len(self.tournament.orig_ids), len(self.tournament.players))
        self.assertTrue(self.player_1 in self.tournament.orig_ids)

        # make sure doesn't overwrite when setting orig_ids specially
        orig_ids = [self.player_5, self.player_2, self.player_3, self.player_4]
        new_tournament = Tournament(
                    name=self.name,
                    source_type=self.source_type,
                    date=self.date,
                    regions=self.regions,
                    raw=self.raw,
                    players=self.players,
                    matches=self.matches,
                    orig_ids=orig_ids)

        new_tournament.save()
        self.assertEqual(len(new_tournament.orig_ids), len(new_tournament.players))
        self.assertTrue(self.player_1 in new_tournament.players)
        self.assertFalse(self.player_5 in new_tournament.players)
        self.assertFalse(self.player_1 in new_tournament.orig_ids)
        self.assertTrue(self.player_5 in new_tournament.orig_ids)

    def test_validate_players_neq_matches(self):
        more_players = self.players + [self.player_5]

        bad_tournament =  self.tournament = Tournament(
                            name=self.name,
                            source_type=self.source_type,
                            date=self.date,
                            regions=self.regions,
                            raw=self.raw,
                            players=more_players,
                            matches=self.matches)

        with self.assertRaises(ValidationError) as cm:
            bad_tournament.save()
        self.assertTrue("set of players in players differs from set of players in matches" in cm.exception.message)

        more_matches = self.matches + [Match(winner=self.player_5, loser=self.player_6)]

        bad_tournament_2 =  self.tournament = Tournament(
                                name=self.name,
                                source_type=self.source_type,
                                date=self.date,
                                regions=self.regions,
                                raw=self.raw,
                                players=self.players,
                                matches=more_matches)

        with self.assertRaises(ValidationError) as cm:
            bad_tournament_2.save()
        self.assertTrue("set of players in players differs from set of players in matches" in cm.exception.message)

    def test_validate_self_play(self):
        bad_match = Match(winner=self.player_1, loser=self.player_1)
        bad_matches = self.matches + [bad_match]

        bad_tournament =  self.tournament = Tournament(
                            name=self.name,
                            source_type=self.source_type,
                            date=self.date,
                            regions=self.regions,
                            raw=self.raw,
                            players=self.players,
                            matches=bad_matches)

        with self.assertRaises(ValidationError) as cm:
            bad_tournament.save()
        self.assertTrue("tournament contains match where player plays themself" in cm.exception.message)

    def test_validate_no_merged_players(self):
        merged_player = Player(name='gaR',
                                merged=True,
                                merge_parent=self.player_1)

        merge_match = Match(winner=merged_player, loser=self.player_4)

        bad_players = self.players + [merged_player]
        bad_matches = self.matches + [merge_match]

        bad_tournament =  self.tournament = Tournament(
                            name=self.name,
                            source_type=self.source_type,
                            date=self.date,
                            regions=self.regions,
                            raw=self.raw,
                            players=bad_players,
                            matches=bad_matches)

        with self.assertRaises(ValidationError) as cm:
            bad_tournament.save()
        self.assertTrue("player in tournament has been merged" in cm.exception.message)

    def test_validate_len_orig_ids(self):
        bad_orig_ids = [self.player_5]
        bad_tournament = Tournament(name=self.name,
                    source_type=self.source_type,
                    date=self.date,
                    regions=self.regions,
                    raw=self.raw,
                    players=self.players,
                    matches=self.matches,
                    orig_ids=bad_orig_ids)
        with self.assertRaises(ValidationError) as cm:
            bad_tournament.save()
        self.assertTrue("different number of orig_ids and players" in cm.exception.message)

    def test_to_string(self):
        self.assertEqual(str(self.tournament), "tournament (2016-01-01)")

    def test_replace_player(self):
        self.assertTrue(self.player_3 in self.tournament.players)
        self.assertTrue(self.tournament.matches[1].contains_player(self.player_3.id))

        self.assertFalse(self.player_5 in self.tournament.players)
        for match in self.tournament.matches:
            self.assertFalse(match.contains_player(self.player_5.id))

        self.assertEqual(len(self.tournament.players), 4)

        self.tournament.replace_player(player_to_remove=self.player_3, player_to_add=self.player_5)
        self.tournament.save()

        self.assertFalse(self.player_3 in self.tournament.players)
        for match in self.tournament.matches:
            self.assertFalse(match.contains_player(self.player_3.id))

        self.assertTrue(self.player_5 in self.tournament.players)
        self.assertTrue(self.tournament.matches[1].contains_player(self.player_5.id))

        self.assertEqual(len(self.tournament.players), 4)

    def test_replace_player_none(self):
        with self.assertRaises(TypeError):
            self.tournament.replace_player(player_to_add=self.player_1)

        with self.assertRaises(TypeError):
            self.tournament.replace_player(player_to_remove=self.player_1)

    def test_replace_player_invalid_player_to_remove(self):
        self.assertTrue(self.player_1 in self.tournament.players)
        self.assertTrue(self.player_2 in self.tournament.players)
        self.assertTrue(self.player_3 in self.tournament.players)
        self.assertTrue(self.player_4 in self.tournament.players)
        self.assertEqual(len(self.tournament.players), 4)

        self.tournament.replace_player(player_to_remove=self.player_5, player_to_add=self.player_6)

        self.assertTrue(self.player_1 in self.tournament.players)
        self.assertTrue(self.player_2 in self.tournament.players)
        self.assertTrue(self.player_3 in self.tournament.players)
        self.assertTrue(self.player_4 in self.tournament.players)
        self.assertEqual(len(self.tournament.players), 4)

    def test_from_pending_tournament(self):
        # we need MatchResults with aliases (instead of IDs)
        match_1 = AliasMatch(winner=self.player_1.name, loser=self.player_2.name)
        match_2 = AliasMatch(winner=self.player_3.name, loser=self.player_4.name)

        aliases = [p.name for p in self.players]
        alias_matches = [match_1, match_2]
        alias_mappings = [
                        AliasMapping(player_alias=self.player_1.name, player=self.player_1),
                        AliasMapping(player_alias=self.player_2.name, player=self.player_2),
                        AliasMapping(player_alias=self.player_3.name, player=self.player_3),
                        AliasMapping(player_alias=self.player_4.name, player=self.player_4)]

        pending_tournament = PendingTournament(
                    name=self.name,
                    source_type=self.source_type,
                    date=self.date,
                    regions=self.regions,
                    raw=self.raw,
                    aliases=aliases,
                    alias_matches=alias_matches,
                    alias_mappings=alias_mappings)
        pending_tournament.save()

        tournament = Tournament.from_pending_tournament(pending_tournament)
        tournament.save()

        self.assertEqual(tournament.name, self.name)
        self.assertEqual(tournament.source_type, self.source_type)
        self.assertEqual(tournament.date, self.date)
        self.assertEqual(tournament.regions, self.regions)
        self.assertEqual(tournament.raw, self.raw)
        self.assertEqual(tournament.matches, self.matches)
        self.assertEqual(tournament.players, self.players)
        self.assertEqual(tournament.orig_ids, self.players)

class TestPendingTournament(unittest.TestCase):
    def setUp(self):
        connect_test_db()

        self.norcal = Region(id='norcal', display_name='Norcal')
        self.texas = Region(id='texas', display_name='Texas')

        self.norcal.save()
        self.texas.save()

        self.player_1 = Player(name='gar')
        self.player_2 = Player(name='sfat')
        self.player_3 = Player(name='shroomed')
        self.player_4 = Player(name='ppu')
        self.player_5 = Player(name='ss')
        self.player_6 = Player(name='hmw')

        self.player_1.save()
        self.player_2.save()
        self.player_3.save()
        self.player_4.save()
        self.player_5.save()
        self.player_6.save()

        self.match_1 = Match(winner=self.player_1, loser=self.player_2)
        self.match_2 = Match(winner=self.player_3, loser=self.player_4)

        self.alias_match_1 = AliasMatch(winner=self.player_1.name, loser=self.player_2.name)
        self.alias_match_2 = AliasMatch(winner=self.player_3.name, loser=self.player_4.name)

        self.players = [self.player_1, self.player_2, self.player_3, self.player_4]
        self.aliases = [p.name for p in self.players]
        self.alias_matches = [self.alias_match_1, self.alias_match_2]
        self.alias_mappings = [
                        AliasMapping(player_alias=self.player_1.name, player=self.player_1),
                        AliasMapping(player_alias=self.player_2.name, player=self.player_2),
                        AliasMapping(player_alias=self.player_3.name, player=self.player_3)]

        self.name = 'tournament'
        self.source_type = 'tio'
        self.date = datetime(2016,1,1)
        self.regions = [self.norcal, self.texas]
        self.raw = 'raw'

        self.pending_tournament = PendingTournament(
                    name=self.name,
                    source_type=self.source_type,
                    date=self.date,
                    regions=self.regions,
                    raw=self.raw,
                    aliases=self.aliases,
                    alias_matches=self.alias_matches,
                    alias_mappings=self.alias_mappings)

        self.pending_tournament.save()

    def test_validate_players_neq_matches(self):
        bad_alias_matches_1 = [self.alias_match_1]
        bad_pending_1 = PendingTournament(
                    name=self.name,
                    source_type=self.source_type,
                    date=self.date,
                    regions=self.regions,
                    raw=self.raw,
                    aliases=self.aliases,
                    alias_matches=bad_alias_matches_1,
                    alias_mappings=self.alias_mappings)

        with self.assertRaises(ValidationError) as cm:
            bad_pending_1.save()
        self.assertTrue("set of players in players differs from set of players in matches" in cm.exception.message)

        bad_alias_matches_2 = [self.alias_match_1, self.alias_match_2, AliasMatch(winner='Emanon', loser='Mango')]
        bad_pending_2 = PendingTournament(
                    name=self.name,
                    source_type=self.source_type,
                    date=self.date,
                    regions=self.regions,
                    raw=self.raw,
                    aliases=self.aliases,
                    alias_matches=bad_alias_matches_2,
                    alias_mappings=self.alias_mappings)

        with self.assertRaises(ValidationError) as cm:
            bad_pending_2.save()
        self.assertTrue("set of players in players differs from set of players in matches" in cm.exception.message)

    def test_validate_mappings_subset_players(self):
        bad_mappings = self.alias_mappings + [AliasMapping(player_alias=self.player_5.name, player=self.player_5)]
        bad_pending = PendingTournament(
                    name=self.name,
                    source_type=self.source_type,
                    date=self.date,
                    regions=self.regions,
                    raw=self.raw,
                    aliases=self.aliases,
                    alias_matches=self.alias_matches,
                    alias_mappings=bad_mappings)

        with self.assertRaises(ValidationError) as cm:
            bad_pending.save()
        self.assertTrue("alias mappings contains mapping for alias not in tournament" in cm.exception.message)

    def test_to_string(self):
        self.assertEqual(str(self.pending_tournament), "tournament (2016-01-01)")

    def test_set_alias_mapping_new(self):
        self.assertEqual(len(self.pending_tournament.alias_mappings), 3)

        new_alias = self.player_4.name
        self.pending_tournament.set_alias_mapping(new_alias, self.player_4)

        self.assertEqual(len(self.pending_tournament.alias_mappings), 4)
        mapping = self.pending_tournament.alias_mappings[3]
        self.assertEqual(mapping['player_alias'], new_alias)
        self.assertEqual(mapping['player'], self.player_4)

    def test_set_alias_mapping_existing(self):
        self.assertEqual(len(self.pending_tournament.alias_mappings), 3)

        self.pending_tournament.set_alias_mapping(self.player_1.name, self.player_5)

        self.assertEqual(len(self.pending_tournament.alias_mappings), 3)
        mapping = self.pending_tournament.alias_mappings[0]
        self.assertEqual(mapping['player_alias'], self.player_1.name)
        self.assertEqual(mapping['player'], self.player_5)

    def test_delete_alias_mapping(self):
        self.assertEqual(len(self.pending_tournament.alias_mappings), 3)
        deleted_mapping = self.pending_tournament.alias_mappings[0]
        self.pending_tournament.delete_alias_mapping(self.player_1.name)
        self.assertEqual(len(self.pending_tournament.alias_mappings), 2)
        self.assertFalse(deleted_mapping in self.pending_tournament.alias_mappings)

    def test_from_scraper(self):
        mock_scraper = mock.Mock(spec=ChallongeScraper)

        mock_scraper.get_players.return_value = self.aliases
        mock_scraper.get_matches.return_value = self.alias_matches
        mock_scraper.get_raw.return_value = self.raw
        mock_scraper.get_date.return_value = self.date
        mock_scraper.get_name.return_value = self.name

        pending_tournament = PendingTournament.from_scraper(self.source_type, mock_scraper, [self.norcal])
        pending_tournament.save()

        self.assertEqual(pending_tournament.name, self.name)
        self.assertEqual(pending_tournament.source_type, self.source_type)
        self.assertEqual(pending_tournament.date, self.date)
        self.assertEqual(pending_tournament.regions, [self.norcal])
        self.assertEqual(pending_tournament.raw, self.raw)
        self.assertEqual(pending_tournament.aliases, self.aliases)
        self.assertEqual(pending_tournament.alias_matches, self.alias_matches)

class TestUser(unittest.TestCase):
    def setUp(self):
        connect_test_db()

        self.norcal = Region(id='norcal', display_name='Norcal')
        self.texas = Region(id='texas', display_name='Texas')
        self.norcal.save()
        self.texas.save()

        self.username = "bob"
        self.salt = "test"
        self.hashed_password = "test"
        self.admin_regions = [self.norcal, self.texas]
        self.user = User(username=self.username,
                         salt=self.salt,
                         hashed_password=self.hashed_password,
                         admin_regions=self.admin_regions)
        self.user.save()

    def test_to_string(self):
        self.assertEqual(str(self.user), self.username)
