import datetime
import os
import re
import sys

from bson import json_util
from bson.objectid import ObjectId
from datetime import datetime
from flask import Flask, request, jsonify
from flask.ext import restful
from flask.ext.restful import reqparse, abort as flask_abort
from flask.ext.cors import CORS
from mongoengine import connect
from mongoengine.base import BaseDocument
from mongoengine.queryset import QuerySet

import alias_service
import rankings

from config.config import Config
from dao import Dao
from model import *
from scraper.tio import TioScraper
from scraper.challonge import ChallongeScraper
from scraper.smashgg import SmashGGScraper

# TODO: pull from config
BASE_REGION = 'newjersey'

app = Flask(__name__)
api = restful.Api(app)

def connect_db():
    # parse config file and open connection
    config = Config()
    mongo_connection = connect(config.get_db_name())
    mongo_connection.the_database.authenticate(config.get_db_user(),
                                               config.get_db_password(),
                                               source=config.get_auth_db_name())

def abort(status_code, body=None):
    error_data = {}
    error_data['status_code'] = status_code
    if body:
        error_data['message'] = str(body)

    flask_abort(status_code, description=body)

def get_dao(region):
    dao = Dao(region)
    if not dao.region:
        abort(404, 'region does not exist')
    return dao

def auth_user(request, dao, check_regions=True):
    session_id = request.cookies.get('session_id')
    user = dao.get_user_by_session_id_or_none(session_id)
    if not user:
        abort(403, "Permission denied")
    if check_regions and dao.region not in user.admin_regions:
        abort(403, "Permission denied")
    return user

# make mongoengines to_json routine consistent with earlier format
def responsify(response):
    #print response, type(response)
    if isinstance(response, BaseDocument):
        return responsify(response.to_mongo())
    elif isinstance(response, QuerySet):
        return list(response)
    elif isinstance(response, datetime):
        return response.strftime("%x")
    elif isinstance(response, ObjectId):
        return str(response)
    elif isinstance(response, dict):
        if '_id' in response:
            response['id'] = response['_id']
            del response['_id']
        return {key: responsify(response[key]) for key in response}
    elif (isinstance(response, list) or isinstance(response, tuple)):
        return [responsify(obj) for obj in response]
    else:
        return response

# wrappers for DAO routines that abort when appropriate

def _get_player_by_id(dao, id):
    try:
        player = dao.get_player_by_id(ObjectId(id))
    except:
        abort(400, 'Invalid ObjectID')

    if not player:
        abort(404, 'Player not found')

    return player

def _get_tournament_by_id(dao, id):
    try:
        oid = ObjectId(id)
    except:
        abort(400, 'Invalid ObjectID')

    tournament = dao.get_tournament_by_id(oid)
    if tournament:
        return tournament

    tournament = dao.get_pending_tournament_by_id(oid)
    if tournament:
        return tournament

    abort(404, 'tournament not found')

#TODO: major refactor to move auth code to a decorator

def is_allowed_origin(origin):
    dragon = r"http(s)?:\/\/(stage\.|www\.)?(notgarpr\.com|192\.168\.33\.1(0)?|njssbm\.com)(\:[\d]*)?$"
    return re.match(dragon, origin)

class RegionListResource(restful.Resource):
    def get(self):
        return_dict = {'regions': Dao.get_all_regions()}

        return responsify(return_dict)

class PlayerListResource(restful.Resource):
    def get(self, region):
        dao = get_dao(region)

        player_list_get_parser = reqparse.RequestParser()
        player_list_get_parser.add_argument('alias', type=str)
        player_list_get_parser.add_argument('all', type=bool)

        args = player_list_get_parser.parse_args()

        return_dict = {}

        if args['alias']:
            # single player matching alias within region
            db_player = dao.get_player_by_alias(args['alias'])
            if db_player:
                return_dict['players'] = [db_player]
            else:
                return_dict['players'] = []
        elif args['all']:
            # get all players in all regions
            return_dict['players'] = dao.get_all_players(all_regions=True)
        else:
            # all players within region
            return_dict['players'] = dao.get_all_players()

        return responsify(return_dict)

class PlayerResource(restful.Resource):
    def get(self, region, id):
        dao = get_dao(region)
        player = _get_player_by_id(dao, id)

        return responsify(player)

    def put(self, region, id):
        dao = get_dao(region)
        auth_user(request, dao)

        player_put_parser = reqparse.RequestParser()
        player_put_parser.add_argument('name', type=str)
        player_put_parser.add_argument('aliases', type=list)
        player_put_parser.add_argument('regions', type=list)
        args = player_put_parser.parse_args()

        player = _get_player_by_id(dao, id)

        if args['name']:
            player.name = args['name']
        if args['aliases'] is not None:
            for a in args['aliases']:
                if not isinstance(a, unicode):
                    return abort(400, "each alias must be a string")
            new_aliases = [a.lower() for a in args['aliases']]
            if player.name.lower() not in new_aliases:
                abort(400, "aliases must contain the players name!")
            player.aliases = new_aliases
        if args['regions'] is not None:
            player.regions = []
            for region_id in args['regions']:
                region = Dao.get_region_by_id(region_id)
                if region:
                    player.regions.append(region)
                else:
                    abort(404, "Invalid region ID {}".format(region_id))

        try:
            player.save()
        except:
            abort(400, "error saving player")

        return responsify(player)

class TournamentListResource(restful.Resource):
    def get(self, region):
        dao = get_dao(region)

        tournament_list_get_parser = reqparse.RequestParser()
        tournament_list_get_parser.add_argument('includePending', type=str, default='false')
        args = tournament_list_get_parser.parse_args()

        if args['includePending']=='true':
            auth_user(request, dao)

        return_dict = {}

        exclude_properties = ['raw', 'matches', 'players', 'orig_ids']
        tournaments = dao.get_all_tournaments(regions=[dao.region],
                                              exclude_properties=exclude_properties)
        return_dict['tournaments'] = tournaments

        if args['includePending']=='true':
            print args['includePending']
            exclude_properties = ['raw', 'aliases', 'alias_matches']
            pending_tournaments = dao.get_all_pending_tournaments(
                                        regions=[dao.region],
                                        exclude_properties=exclude_properties)
            return_dict['pending_tournaments'] = pending_tournaments

        return responsify(return_dict)

    def post(self, region):
        dao = get_dao(region)
        auth_user(request, dao)

        tournament_list_post_parser = reqparse.RequestParser()
        tournament_list_post_parser.add_argument('type', type=str, location='json')
        tournament_list_post_parser.add_argument('data', type=unicode, location='json')
        tournament_list_post_parser.add_argument('bracket', type=str, location='json')

        args = tournament_list_post_parser.parse_args()

        if args['data'] is None:
            abort(400, "data required")

        the_bytes = bytearray(args['data'], "utf8")

        if the_bytes[0] == 0xef:
            print "found magic numbers"
            abort(503, "magic numbers!")

        source_type = args['type']
        data = args['data']
        pending_tournament = None

        if source_type == 'tio':
            if args['bracket'] is None:
                abort(400, "Missing bracket name")
            data_bytes = bytes(data)
            if data_bytes[0] == '\xef':
                data = data[:3]
            scraper = TioScraper(data, args['bracket'])
        elif source_type == 'challonge':
            scraper = ChallongeScraper(data)
        elif source_type == 'smashgg':
            scraper = SmashGGScraper(data)
        else:
            abort(400, "Unknown type")

        try:
            pending_tournament = PendingTournament.from_scraper(source_type, scraper, [dao.region])
        except:
            abort(400, 'Scraper encountered an error')
        if not pending_tournament:
            abort(400, 'Scraper encountered an error')

        try:
            pending_tournament.alias_mappings = alias_service.get_alias_mappings(dao, pending_tournament.aliases)
        except:
            abort(400, 'Alias service encountered an error')

        try:
            pending_tournament.save()
            return_dict = {
                'id': pending_tournament.id
            }
            return responsify(return_dict)
        except:
            abort(400, 'insert_pending_tournament encountered an error')

        abort(400, 'Unknown error!')

class TournamentResource(restful.Resource):
    def get(self, region, id):
        dao = get_dao(region)

        tournament = _get_tournament_by_id(dao, id)
        return_dict = {}

        if isinstance(tournament, Tournament):
            return_dict['tournament'] = tournament
            return_dict['players'] = [{
                'id': p.id,
                'name': p.name
                } for p in tournament.players]
            return_dict['matches'] = [{
                'winner_id': m.winner.id,
                'winner_name': m.winner.name,
                'loser_id': m.loser.id,
                'loser_name': m.loser.name
                } for m in tournament.matches]
        elif isinstance(tournament, PendingTournament):
            auth_user(request, dao)
            return_dict['tournament'] = tournament
        else:
            abort(400, 'error loading tournament')

        return responsify(return_dict)

    def put(self, region, id):
        dao = get_dao(region)
        user = auth_user(request, dao)

        tournament_put_parser = reqparse.RequestParser()
        tournament_put_parser.add_argument('name', type=str)
        tournament_put_parser.add_argument('date', type=str)
        tournament_put_parser.add_argument('players', type=list)
        tournament_put_parser.add_argument('matches', type=list)
        tournament_put_parser.add_argument('regions', type=list)
        tournament_put_parser.add_argument('pending', type=bool)
        args = tournament_put_parser.parse_args()

        tournament = _get_tournament_by_id(dao, id)

        try:
            if args['name']:
                tournament.name = args['name']
            if args['date']:
                try:
                    tournament.date = datetime.strptime(args['date'].strip(), '%m/%d/%y')
                except:
                    abort(400, "Invalid date format")
            if args['regions']:
                tournament.regions = [Dao.get_region_by_id(r) for r in args['regions']]

            if isinstance(tournament, Tournament):
                if args['players']:
                    tournament.orig_ids = []
                    tournament.players = [ObjectId(pid) for pid in args['players']]
                if args['matches']:
                    tournament.matches = [Match(winner=ObjectId(m['winner']), loser=ObjectId(m['loser'])) for m in args['matches']]

            elif isinstance(tournament, PendingTournament):
                if args['players']:
                    tournament.aliases = args['players']
                if args['matches']:
                    tournament.alias_matches = [AliasMatch(winner=m['winner'],
                                                           loser=m['loser'])
                                                        for m in args['matches']]
        except:
            abort(400, "Error parsing tournament data")

        try:
            tournament.save()
        except Exception as e:
            print e
            abort(400, "Error saving tournament")

        return responsify(tournament)

    def delete(self, region, id):
        """ Deletes a tournament.
            Route restricted to admins for this region.
            Be VERY careful when using this """
        dao = get_dao(region)
        auth_user(request, dao)

        tournament = _get_tournament_by_id(dao, id)

        try:
            tournament.delete()
        except:
            abort(400, "Error deleting tournament")
        return {"success": True}

class PendingTournamentResource(restful.Resource):
    """
    Updates alias_mappings for the pending tournament
    """
    def put(self, region, id):
        dao = get_dao(region)
        auth_user(request, dao)

        pending_tournament_put_parser = reqparse.RequestParser()
        pending_tournament_put_parser.add_argument('alias_mappings', type=list)
        args = pending_tournament_put_parser.parse_args()

        pending_tournament = None
        try:
            pending_tournament = dao.get_pending_tournament_by_id(ObjectId(id))
        except:
            abort(400, "Invalid ObjectId")
        if not pending_tournament:
            abort(404, "No pending touranment found with that ID")

        try:
            for alias_item in args["alias_mappings"]:
                player_alias = alias_item["player_alias"]
                player_id = ObjectId(alias_item["player_id"])
                pending_tournament.set_alias_mapping(player_alias, player_id)
        except:
            abort(400, 'Error processing alias_mappings')

        try:
            pending_tournament.save()
            return responsify(pending_tournament)
        except:
            abort(400, 'Encountered an error inserting pending tournament')

class FinalizeTournamentResource(restful.Resource):
    """ Converts a pending tournament to a tournament.
        Works only if the PendingTournament's alias_to_id_map is completely filled out.
        Route restricted to admins for this region. """
    def post(self, region, id):
        dao = get_dao(region)
        auth_user(request, dao)

        pending_tournament = None
        try:
            pending_tournament = dao.get_pending_tournament_by_id(ObjectId(id))
        except:
            abort(400, 'Invalid ObjectID')
        if not pending_tournament:
            abort(400, 'No pending tournament found with that id.')

        new_player_names = []
        for mapping in pending_tournament.alias_mappings:
            if mapping.player == None:
                new_player_names.append(mapping.player_alias)

        for player_name in new_player_names:
            player = Player(name=player_name, regions=[dao.region])
            try:
                player.save()
            except:
                abort(400, "Error saving new player")
            pending_tournament.set_alias_mapping(player_name, player)

        try:
            # save pending_tournament to validate it
            pending_tournament.save()
            tournament = Tournament.from_pending_tournament(pending_tournament)
            tournament.save()
            pending_tournament.delete()
            return {"success": True, "tournament_id": str(tournament.id)}
        except ValueError:
            abort(400, 'Not all player aliases in this pending tournament have been mapped to player ids.')
        except:
            abort(400, 'Dao threw an error somewhere')

class RankingsResource(restful.Resource):
    def get(self, region):
        dao = get_dao(region)

        latest_ranking = dao.get_latest_ranking()
        if not latest_ranking:
            abort(404, 'No ranking in system')

        return_dict = {}
        return_dict['ranking'] = latest_ranking
        return_dict['ranking_entries'] = [{
            'rank': r.rank,
            'name': r.player.name,
            'player_id': r.player.id,
            'rating': r.rating
        } for r in latest_ranking.rankings]

        return responsify(return_dict)

    def post(self, region):
        dao = get_dao(region)
        auth_user(request, dao)

        rankings.generate_ranking(dao, now=datetime.now())

        return self.get(region)

class MatchesResource(restful.Resource):
    def get(self, region, id):
        dao = get_dao(region)

        matches_get_parser = reqparse.RequestParser()
        matches_get_parser.add_argument('opponent', type=str)
        args = matches_get_parser.parse_args()

        return_dict = {}

        player = None
        try:
            player = dao.get_player_by_id(ObjectId(id))
        except:
            abort(400, 'Invalid ObjectID')
        if not player:
            abort(404, "Player not found")

        return_dict['matches'] = []
        return_dict['wins'] = 0
        return_dict['losses'] = 0

        if player.merged:
            # no need to look up tournaments for merged players
            return responsify(return_dict)

        return_dict['player'] = player
        player_list = [player]

        opponent_id = args['opponent']
        if opponent_id is not None:
            try:
                opponent = dao.get_player_by_id(ObjectId(args['opponent']))
                return_dict['opponent'] = opponent
                player_list.append(opponent)
            except:
                abort('Invalid ObjectID', 400)

        tournaments = dao.get_all_tournaments(players=player_list)
        for tournament in tournaments:
            for match in tournament.matches:
                if (opponent_id is not None and match.contains_players(player.id, opponent.id)) or \
                        (opponent_id is None and match.contains_player(player.id)):
                    match_dict = {}
                    match_dict['tournament_id'] = tournament.id
                    match_dict['tournament_name'] = tournament.name
                    match_dict['tournament_date'] = tournament.date
                    opp_player = match.get_opposing_player(player.id)
                    match_dict['opponent_id'] = opp_player.id
                    match_dict['opponent_name'] = opp_player.name
                    if match.did_player_win(player.id):
                        match_dict['result'] = 'win'
                        return_dict['wins'] += 1
                    else:
                        match_dict['result'] = 'lose'
                        return_dict['losses'] += 1

                    return_dict['matches'].append(match_dict)

        return responsify(return_dict)


class MergeListResource(restful.Resource):
    def get(self, region):
        dao = get_dao(region)
        auth_user(request, dao)

        return_dict = {}
        return_dict['merges'] = {'merge': merge for merge in dao.get_all_merges()}

        for merge in return_dict['merges']:
            merge_obj = merge['merge']

            merge['source_player_name'] = merge_obj.source_player.name
            merge['target_player_name'] = merge_obj.target_player.name
            merge['requester_name'] = merge_obj.requester.username;

        return responsify(return_dict)

    def put(self, region):
        dao = get_dao(region)
        user = auth_user(request, dao)

        merges_put_parser = reqparse.RequestParser()
        merges_put_parser.add_argument('source_player_id', type=str)
        merges_put_parser.add_argument('target_player_id', type=str)
        args = merges_put_parser.parse_args()

        try:
            source_player_id = ObjectId(args['source_player_id'])
            target_player_id = ObjectId(args['target_player_id'])
        except:
            abort(400, "invalid ids, that wasn't an ObjectID")

        source_player = dao.get_player_by_id(source_player_id)
        target_player = dao.get_player_by_id(target_player_id)

        if not source_player:
            abort(400, "source player not found")
        if not target_player:
            abort(400, "target player not found")

        the_merge = Merge(requester=user,
                          source_player=source_player,
                          target_player=target_player,
                          time=datetime.now())

        try:
            dao.insert_merge(the_merge)
            return_dict = {'status': "success", 'id': str(the_merge.id)}
            return return_dict, 200
        except Exception as e:
            print 'error merging players: ' + str(e)
            abort(400, 'error merging players: ' + str(e))

class MergeResource(restful.Resource):
    def get(self, region, id):
        # TODO: decide if we want this
        pass

    def delete(self, region, id):
        dao = get_dao(region)
        auth_user(request, dao)

        try:
            the_merge = dao.get_merge(ObjectId(id))
            dao.undo_merge(the_merge)
            return "successfully undid merge", 200
        except Exception as e:
            print 'error merging players: ' + str(e)
            return 'error merging players: ' + str(e), 400

class SessionResource(restful.Resource):
    ''' logs a user in. i picked put over post because its harder to CSRF, not that CSRFing login actually matters'''
    def put(self):
        dao = Dao(None)

        session_put_parser = reqparse.RequestParser()
        session_put_parser.add_argument('username', type=str)
        session_put_parser.add_argument('password', type=str)
        args = session_put_parser.parse_args() #parse args

        session_id = dao.check_creds_and_get_session_id_or_none(args['username'], args['password'])
        if not session_id:
            abort(403, 'Permission denied')

        resp = jsonify({"status": "connected"})
        resp.set_cookie('session_id', session_id)
        return resp

    ''' logout, destroys session_id mapping on client and server side '''
    def delete(self):
        dao = Dao(None)

        session_delete_parser = reqparse.RequestParser()
        session_delete_parser.add_argument('session_id', location='cookies', type=str)
        args = session_delete_parser.parse_args()

        logout_success = dao.logout_user_or_none(args['session_id'])
        if not logout_success:
            abort(404, 'who is you')

        return 'logout success', 200, {'Set-Cookie': "session_id=deleted; expires=Thu, 01 Jan 1970 00:00:00 GMT"}

    def get(self):
        dao = Dao(None)
        user = auth_user(request, dao, check_regions=False)

        # don't return salt + hashed_password!
        return_dict = {'username': user.username,
                       'admin_regions': user.admin_regions}

        return responsify(return_dict)

@app.after_request
def add_security_headers(resp):
    resp.headers['Strict-Transport-Security'] = "max-age=31536000; includeSubdomains"
    resp.headers['Content-Security-Policy'] = "default-src https: data: 'unsafe-inline' 'unsafe-eval'"
    resp.headers['X-Frame-Options'] = "DENY"
    resp.headers['X-XSS-Protection'] = "1; mode=block"
    resp.headers['X-Content-Type-Options'] = "nosniff"
    return resp

@app.after_request
def add_cors(resp):
    """ Ensure all responses have the CORS headers. This ensures any failures are also accessible
        by the client. """
    the_origin = request.headers.get('Origin','*')
    if not is_allowed_origin(the_origin):
        return resp
    resp.headers['Access-Control-Allow-Origin'] =  the_origin
    resp.headers['Access-Control-Allow-Credentials'] = 'true'
    resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS, GET, PUT, DELETE'
    resp.headers['Access-Control-Allow-Headers'] = request.headers.get('Access-Control-Request-Headers', 'Authorization' )
    resp.headers["Access-Control-Expose-Headers"] = "Set-Cookie"
    # set low for debugging
    if app.debug:
        resp.headers['Access-Control-Max-Age'] = '1'
    return resp


api.add_resource(MergeResource, '/<string:region>/merges/<string:id>')
api.add_resource(MergeListResource, '/<string:region>/merges')

api.add_resource(RegionListResource, '/regions')

api.add_resource(PlayerListResource, '/<string:region>/players')
api.add_resource(PlayerResource, '/<string:region>/players/<string:id>')

api.add_resource(MatchesResource, '/<string:region>/matches/<string:id>')

api.add_resource(TournamentListResource, '/<string:region>/tournaments')
api.add_resource(TournamentResource, '/<string:region>/tournaments/<string:id>')
api.add_resource(PendingTournamentResource, '/<string:region>/pending_tournaments/<string:id>')
api.add_resource(FinalizeTournamentResource, '/<string:region>/tournaments/<string:id>/finalize')

api.add_resource(RankingsResource, '/<string:region>/rankings')

api.add_resource(SessionResource, '/users/session')

if __name__ == '__main__':
    connect_db()
    app.run(host='0.0.0.0', port=int(sys.argv[1]), debug=(sys.argv[2] == 'True'))
