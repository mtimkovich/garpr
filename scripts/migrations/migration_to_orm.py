# initial script for migrating everything over to the ORM
# should only need to be run once; for an example of a normal migration,
# see other scripts in this folder

import os
import sys

from mongoengine import connect
from pymongo import MongoClient

# add root directory to python path
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/../../'))

from config.config import Config
from model import *

config = Config()
OLD_DB_NAME = config.get_db_name()
TMP_DB_NAME = 'garpr_tmp'
OLD_BACKUP_DB_NAME = 'garpr_old'

MODELS = [Merge,
          Player,
          Region,
          Ranking,
          Session,
          Tournament,
          PendingTournament,
          User]

def migrate_to_orm():
    # connect with PyMongo to old and tmp dbs
    mongo_client = MongoClient(host=config.get_mongo_url())
    old_db = mongo_client.get_database(OLD_DB_NAME)
    mongo_client.drop_database(TMP_DB_NAME)
    new_db = mongo_client.get_database(TMP_DB_NAME)

    print 'Migrating merges...'
    old_merges = old_db.get_collection('merges')
    new_merges = new_db.get_collection('merge')
    requests = []
    for old_merge in old_merges.find():
        new_merge = {'_id': old_merge.get('_id'),
                     'requester': old_merge.get('requester_user_id')[8:],
                     'source_player': old_merge.get('source_player_obj_id'),
                     'target_player': old_merge.get('target_player_obj_id'),
                     'time': old_merge.get('time')}
        try:
            new_merges.insert_one(new_merge)
        except Exception as e:
            print e

    print 'Migrating players...'
    old_players = old_db.get_collection('players')
    new_players = new_db.get_collection('player')
    requests = []
    for old_player in old_players.find():
        new_ratings = [{'region': region,
                        'mu': rating.get('mu'),
                        'sigma': rating.get('sigma')}
                        for region,rating in old_player.get('ratings').items()]
        new_player = {'_id': old_player.get('_id'),
                      'name': old_player.get('name'),
                      'aliases': old_player.get('aliases'),
                      'ratings': new_ratings,
                      'regions': old_player.get('regions'),
                      'merged': old_player.get('merged'),
                      'merge_parent': old_player.get('merge_parent'),
                      'merge_children': old_player.get('merge_children')}
        if new_player['merge_children'] and new_player['_id'] in new_player['merge_children']:
            new_player['merge_children'].remove(new_player['_id'])
        try:
            new_players.insert_one(new_player)
        except Exception as e:
            print e

    print 'Migrating regions...'
    old_regions = old_db.get_collection('regions')
    new_regions = new_db.get_collection('region')
    for old_region in old_regions.find():
        new_region = {'_id': old_region.get('_id'),
                    'display_name': old_region.get('display_name')}
        try:
            new_regions.insert_one(new_region)
        except Exception as e:
            print e

    print 'Migrating rankings...'
    old_rankings = old_db.get_collection('rankings')
    new_rankings = new_db.get_collection('ranking')
    for old_ranking in old_rankings.find():
        new_ranks = [
            {'rank': rank.get('rank'),
             'player': rank.get('player'),
             'rating': {
                'region': old_ranking.get('region'),
                'mu': rank.get('rating'),
                'sigma': 0.
             }}
             for rank in old_ranking.get('ranking')]
        new_ranking = {'_id': old_ranking.get('_id'),
                       'region': old_ranking.get('region'),
                       'time': old_ranking.get('time'),
                       'rankings': new_ranks,
                       'tournaments': old_ranking.get('tournaments')}
        try:
            new_rankings.insert_one(new_ranking)
        except Exception as e:
            print e

    print 'Migrating sessions...'
    old_sessions = old_db.get_collection('sessions')
    new_sessions = new_db.get_collection('session')
    for old_session in old_sessions.find():
        new_session = {'_id': old_session.get('session_id'),
                       'user': old_session.get('user_id')[8:]}
        try:
            new_sessions.insert_one(new_session)
        except Exception as e:
            print e

    print 'Migrating tournaments...'
    old_tournaments = old_db.get_collection('tournaments')
    new_tournaments = new_db.get_collection('tournament')
    for old_tournament in old_tournaments.find():
        new_tournament = {'_id': old_tournament.get('_id'),
                          'name': old_tournament.get('name'),
                          'source_type': old_tournament.get('type'),
                          'date': old_tournament.get('date'),
                          'regions': old_tournament.get('regions'),
                          'raw': unicode(old_tournament.get('raw')),
                          'players': old_tournament.get('players'),
                          'matches': old_tournament.get('matches'),
                          'orig_ids': old_tournament.get('orig_ids')}
        try:
            new_tournaments.insert_one(new_tournament)
        except Exception as e:
            print e

    print 'Migrating pending tournaments...'
    old_pending_tournaments = old_db.get_collection('pending_tournaments')
    new_pending_tournaments = new_db.get_collection('pending_tournament')
    for old_tournament in old_pending_tournaments.find():
        if 'alias_to_id_map' in old_tournament:
            new_alias_mappings = [{
                    'player_alias': mapping.get('player_alias'),
                    'player': mapping.get('player_id')
                } for mapping in old_tournament.get('alias_to_id_map')]
        else:
            new_alias_mappings = []
        new_tournament = {'_id': old_tournament.get('_id'),
                          'name': old_tournament.get('name'),
                          'source_type': old_tournament.get('type'),
                          'date': old_tournament.get('date'),
                          'regions': old_tournament.get('regions'),
                          'raw': unicode(old_tournament.get('raw')),
                          'aliases': old_tournament.get('players'),
                          'alias_matches': old_tournament.get('matches'),
                          'alias_mappings': new_alias_mappings}
        try:
            new_pending_tournaments.insert_one(new_tournament)
        except Exception as e:
            print e

    print 'Migrating users...'
    old_users = old_db.get_collection('users')
    new_users = new_db.get_collection('user')
    for old_user in old_users.find():
        new_user = {'_id': old_user.get('username'),
                    'salt': old_user.get('salt'),
                    'hashed_password': old_user.get('hashed_password'),
                    'admin_regions': old_user.get('admin_regions')}
        try:
            new_users.insert_one(new_user)
        except Exception as e:
            print e


    print "Validating objects in MongoEngine..."

    # validate objects using MongoEngine
    mongo_connection = connect(TMP_DB_NAME)
    mongo_connection.the_database.authenticate(config.get_db_user(),
                                               config.get_db_password(),
                                               source=config.get_auth_db_name())


    for model_class in MODELS:
        print "Validating {}...".format(model_class)
        for obj in model_class.objects.no_cache():
            try:
                obj.save()
            except ValidationError as e:
                print e
                print "Deleting object", obj
                obj.delete()

    print "Revalidating..."
    for model_class in MODELS:
        print "Validating {}...".format(model_class)
        for obj in model_class.objects.no_cache():
            try:
                obj.save()
            except ValidationError as e:
                print e
                return

    print "Validation successful, renaming DBs..."

    # move old db to OLD_BACKUP_DB_NAME
    print "Renaming {} to {}".format(OLD_DB_NAME, OLD_BACKUP_DB_NAME)
    mongo_client.admin.command('copydb',
                               fromdb=OLD_DB_NAME,
                               todb=OLD_BACKUP_DB_NAME)
    mongo_client.drop_database(OLD_DB_NAME)

    # move new db to OLD_DB_NAME
    print "Renaming {} to {}".format(TMP_DB_NAME, OLD_DB_NAME)
    mongo_client.admin.command('copydb',
                               fromdb=TMP_DB_NAME,
                               todb=OLD_DB_NAME)
    mongo_client.drop_database(TMP_DB_NAME)

if __name__ == "__main__":
    migrate_to_orm()
