from bson.objectid import ObjectId
from datetime import datetime, timedelta
from pymongo import MongoClient, DESCENDING

import base64
import hashlib
import os
import re
import trueskill

from config.config import Config
from model import *

config = Config()

SPECIAL_CHARS = re.compile("[^\w\s]*")
ITERATION_COUNT = 100000

def gen_password(password):
    # more bytes of randomness? i think 16 bytes is sufficient for a salt
    salt = base64.b64encode(os.urandom(16))
    hashed_password = base64.b64encode(hashlib.pbkdf2_hmac('sha256', password, salt, ITERATION_COUNT))

    return salt, hashed_password

def verify_password(password, salt, hashed_password):
    the_hash = base64.b64encode(hashlib.pbkdf2_hmac('sha256', password, salt, ITERATION_COUNT))
    return (the_hash and the_hash==hashed_password)


class Dao(object):
    def __init__(self, region_id):
        self.region = Region.objects.get(id=region_id)

    # sorted by display name
    @classmethod
    def get_all_regions(cls):
        return Region.objects.order_by('display_name')

    def get_player_by_id(self, id):
        try:
            return Player.objects.get(id=id)
        except Player.DoesNotExist:
            return None

    def get_player_by_alias(self, alias, include_merged=False):
        '''Converts alias to lowercase'''
        return Player.objects(
            aliases=alias.lower(),
            regions=self.region,
            merged=False).first()

    def get_players_by_alias_from_all_regions(self, alias, include_merged=False):
        '''Converts alias to lowercase'''
        return list(Player.objects(
            aliases=alias.lower(),
            merged=include_merged))

    def get_player_id_map_from_player_aliases(self, aliases, include_merged=False):
        '''Given a list of player aliases, returns a list of player aliases/id pairs for the current
        region. If no player can be found, the player id field will be set to None.'''
        player_alias_to_player_id_map = []

        for alias in aliases:
            id = None
            player = self.get_player_by_alias(alias, include_merged)
            if player is not None:
                id = player.id

            player_alias_to_player_id_map.append({
                'player_alias': alias,
                'player_id': id
            })

        return player_alias_to_player_id_map

    def get_all_players(self, all_regions=False, include_merged=False):
        '''Sorts by name in lexographical order.'''
        mongo_request = {}
        if not all_regions:
            mongo_request['regions'] = self.region
        if not include_merged:
            mongo_request['merged'] = False

        return list(Player.objects(**mongo_request).order_by('name'))

    def get_all_pending_tournaments(self, regions=None):
        '''players is a list of Players'''
        # TODO: replace with MongoEngine query?
        query_dict = {}
        query_list = []

        if regions:
            query_list.append({'regions': {'$in': regions}})

        if query_list:
            query_dict['$and'] = query_list


        return list(PendingTournament.objects(__raw__=query_dict) \
                                .exclude('raw')      \
                                .order_by('date'))

    def get_pending_tournament_by_id(self, id):
        try:
            return PendingTournament.objects.get(id=id)
        except PendingTournament.DoesNotExist:
            return None

    def get_all_tournament_ids(self, players=None, regions=None):
        return [x.id for x in self.get_all_tournaments(players, regions)]

    def get_all_tournaments(self, players=None, regions=None, op='and'):
        '''players is a list of Players'''
        query_dict = {}
        query_list = []

        if players:
            for player in players:
                query_list.append({'players': {'$in': [player.id]}})

        if regions:
            for region in regions:
                query_list.append({'regions': {'$in': [region.id]}})

        if query_list:
            if op == 'and':
                query_dict['$and'] = query_list
            elif op == 'or':
                query_dict['$or'] = query_list

        return list(Tournament.objects(__raw__=query_dict) \
                         .exclude('raw')              \
                         .order_by('date'))


    def get_tournament_by_id(self, id):
        try:
            return Tournament.objects.get(id=id)
        except Tournament.DoesNotExist:
            return None

    # gets potential merge targets from all regions
    # basically, get players who have an alias similar to the given alias
    def get_players_with_similar_alias(self, alias):
        alias_lower = alias.lower()

        #here be regex dragons
        re_test_1 = '([1-9]+\s+[1-9]+\s+)(.+)' # to match '1 1 slox'
        re_test_2 = '(.[1-9]+.[1-9]+\s+)(.+)' # to match 'p1s1 slox'

        alias_set_1 = re.split(re_test_1, alias_lower)
        alias_set_2 = re.split(re_test_2, alias_lower)

        similar_aliases = [
            alias_lower,
            alias_lower.replace(" ", ""), # remove spaces
            re.sub(SPECIAL_CHARS, '', alias_lower), # remove special characters
            # remove everything before the last special character; hopefully removes crew/sponsor tags
            re.split(SPECIAL_CHARS, alias_lower)[-1].strip()
        ]

        # regex nonsense to deal with pool prefixes
        # prevent index OOB errors when dealing with tags that don't split well
        if len(alias_set_1) == 4:
            similar_aliases.append(alias_set_1[2].strip())
        if len(alias_set_2) == 4:
            similar_aliases.append(alias_set_2[2].strip())


        #add suffixes of the string
        alias_words = alias_lower.split()
        similar_aliases.extend([' '.join(alias_words[i:]) for i in xrange(len(alias_words))])

        # uniqify
        similar_aliases = list(set(similar_aliases))

        return list(Player.objects(aliases__in=similar_aliases,
                                   merged=False))

    def get_merge(self, merge_id):
        try:
            return Merge.objects.get(id=merge_id)
        except Merge.DoesNotExist:
            return None

    def get_all_merges(self):
        return Merge.objects.order_by('time')

    def insert_merge(self, the_merge):
        the_merge.save()
        self.merge_players(the_merge)

    def undo_merge(self, the_merge):
        self.unmerge_players(the_merge)
        the_merge.delete()

    def merge_players(self, merge):
        if merge is None:
            raise TypeError("merge cannot be none")

        source = merge.source_player
        target = merge.target_player

        # update target and source players
        target.aliases = list(set(source.aliases+target.aliases))
        target.regions = list(set(source.regions+target.regions))

        target.merge_children.append(source)
        target.merge_children.extend(source.merge_children)
        source.merge_parent = target
        source.merged = True

        source.save()
        target.save()

        # replace source with target in all tournaments that contain source
        for tournament in self.get_all_tournaments(players=[source]):
            tournament.replace_player(player_to_remove=source, player_to_add=target)
            tournament.save()

    def unmerge_players(self, merge):
        source = merge.source_player
        target = merge.target_player

        if source.merge_parent != target:
            raise ValueError("source not merged into target")

        if target.merged:
            raise ValueError("target has been merged; undo that merge first")

        # TODO: unmerge aliases and regions
        # (probably best way to do this is to store which aliases and regions were merged in the merge Object)
        source.merge_parent = None
        source.merged = False
        target.merge_children = [child for child in target.merge_children if child not in source.merge_children and child!=source]

        source.save()
        target.save()

        # unmerge source from target
        source_players = source.merge_children + [source]

        for tournament in self.get_all_tournaments(players=[source,target], op='or'):
            print tournament
            if target in tournament.players:
                # check if original id now belongs to source
                if any([child in tournament.orig_ids for child in source_players]):
                    print "unmerging tournament", tournament
                    # replace target with source in tournament
                    tournament.replace_player(player_to_remove=target, player_to_add=source)
                    tournament.save()


    def get_latest_ranking(self):
        return Ranking.objects.order_by('-time').first()
        return Ranking.from_json(self.rankings_col.find({'region': self.region_id}).sort('time', DESCENDING)[0])

    # TODO add more tests
    def is_inactive(self, player, now, day_limit, num_tourneys):

        # TODO: handle special cases somewhere properly
        #       (probably in rankings.generate_ranking)

        # special case for Westchester
        if self.region.id == "westchester":
            day_limit = 1500
            num_tourneys = 1

        # special case for NYC
        if self.region.id == "nyc":
            day_limit = 90
            num_tourneys = 3

        cutoff_date = now - timedelta(days=day_limit)
        qualifying_tournaments = Tournament.objects(players=player,
                                            regions=self.region,
                                            date__gte=cutoff_date)

        if len(qualifying_tournaments) >= num_tourneys:
            return False
        return True

    # session management

    def create_user(self, username, password, region_ids):
        valid_regions = Dao.get_all_regions()
        valid_region_ids = [region.id for region in valid_regions]

        for region_id in region_ids:
            if region_id not in valid_region_ids:
                print 'Warning: invalid region name', region_id

        regions = [region for region in valid_regions if region.id in region_ids]
        if len(regions) == 0:
            raise ValueError("No valid region for new user")

        salt, hashed_password = gen_password(password)
        the_user = User(username=username,
                        salt=salt,
                        hashed_password=hashed_password,
                        admin_regions=regions)
        the_user.save()

    def change_passwd(self, username, password):
        try:
            user = User.objects.get(username=username)
            salt, hashed_password = gen_password(password)

            user.salt = salt
            user.hashed_password = hashed_password
            user.save()
        except:
            print "Error: user %s not found" % username

    def get_all_users(self):
        return list(User.objects)

    def get_user_by_id_or_none(self, id):
        return User.objects(id=id).first()

    def get_user_by_username_or_none(self, username):
        return User.objects(username=username).first()

    def get_user_by_session_id_or_none(self, session_id):
        # mongo magic here, go through and get a user by session_id if they exist, otherwise return none
        session = Session.objects(id=session_id).first()
        return session.user if session else None


    #### FOR INTERNAL USE ONLY ####
    #XXX: this method must NEVER be publicly routeable, or you have session-hijacking
    def get_session_id_by_user_or_none(self, user):
        session = Session.objects(user=user).first()
        return session.id if user else None
    #### END OF YELLING #####


    def check_creds_and_get_session_id_or_none(self, username, password):
        user = get_user_by_username_or_none(username)
        if not user:
            return None

         # timing oracle on this... good luck
        if verify_password(password, user.salt, user.hashed_password):
            session_id = base64.b64encode(os.urandom(128))
            self.update_session_id_for_user(user, session_id)
            return session_id
        else:
            return None

    def update_session_id_for_user(self, user, session_id):
        #lets force people to have only one session at a time
        Session.objects(user=user).delete()
        new_session = SessionMapping(id=session_id,
                                     user=user)
        new_session.save()

    def logout_user_or_none(self, session_id):
        user = self.get_user_by_session_id_or_none(session_id)
        if user:
            Session.objects(user=user).delete()
            return True
        return None
