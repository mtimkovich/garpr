from bson.objectid import InvalidId, ObjectId

import collections
import datetime
import trueskill

SOURCE_TYPE_CHOICES = ('tio', 'challonge', 'smashgg', 'other')


class ValidationError(Exception):
    pass

# Fields

# Field decorators

# decorator that handles default serialization for all fields


def serialize_super(none_value=None):
    def serialize_outer(serialize):
        def serialize_wrapper(self, value, context, obj):
            if value is None:
                if callable(none_value):
                    return none_value()
                else:
                    return none_value
            return serialize(self, value, context, obj)
        return serialize_wrapper
    return serialize_outer

# decorator that handles default unserialization for all fields


def unserialize_super(none_value=None):
    def unserialize_outer(unserialize):
        def unserialize_wrapper(self, value, context, data):
            if value is None:
                if callable(none_value):
                    return none_value()
                else:
                    return none_value
            return unserialize(self, value, context, data)
        return unserialize_wrapper
    return unserialize_outer

# decorator that handles default validation for all fields


def validate_super(validate):
    def validate_wrapper(self, value):
        if not Field.validate(self, value):
            return False

        if value is None:
            return True

        return validate(self, value)
    return validate_wrapper


class Field(object):

    def __init__(self, default=None,
                 required=False,
                 validators=None,
                 load_from=None,
                 dump_to=None):
        self.default = default
        self.required = required
        self.validators = validators
        self.load_from = load_from
        self.dump_to = dump_to

    def serialize(self, value, context, obj):
        raise NotImplementedError

    def unserialize(self, value, context, data):
        raise NotImplementedError

    def validate(self, value):
        if self.required and (value is None):
            return False

        if self.validators:
            for validator in self.validators:
                if not validator(value):
                    return False

        return True


class BooleanField(Field):

    @serialize_super()
    def serialize(self, value, context, obj):
        return value

    @unserialize_super()
    def unserialize(self, value, context, data):
        if not isinstance(value, bool):
            return None
        else:
            return value

    @validate_super
    def validate(self, value):
        return isinstance(value, bool)


class DateTimeField(Field):

    @serialize_super()
    def serialize(self, value, context, obj):
        if context == 'db':
            return value
        elif context == 'web':
            return value.strftime("%x")

    @unserialize_super()
    def unserialize(self, value, context, data):
        if context == 'db':
            return value
        elif context == 'web':
            try:
                return datetime.datetime.strptime(value, "%x")
            except ValueError:
                # TODO: log this error
                return None

    @validate_super
    def validate(self, value):
        return isinstance(value, datetime.datetime)


class DictField(Field):

    def __init__(self, from_field, to_field, *args, **kwargs):
        self.from_field = from_field
        self.to_field = to_field
        super(DictField, self).__init__(*args, **kwargs)

    @serialize_super(none_value=dict)
    def serialize(self, value, context, obj):
        return {self.from_field.serialize(k, context, obj): self.to_field.serialize(v, context, obj)
                for k, v in value.items()}

    @unserialize_super(none_value=dict)
    def unserialize(self, value, context, data):
        if not isinstance(value, dict):
            return dict()
        return {self.from_field.unserialize(k, context, data): self.to_field.unserialize(v, context, data)
                for k, v in value.items()}

    @validate_super
    def validate(self, value):
        if not isinstance(value, dict):
            return False

        for k, v in value.items():
            if not self.from_field.validate(k):
                return False
            if not self.to_field.validate(v):
                return False
        return True


class DocumentField(Field):

    def __init__(self, document_type, *args, **kwargs):
        self.document_type = document_type
        super(DocumentField, self).__init__(self, *args, **kwargs)

    @serialize_super()
    def serialize(self, value, context, obj):
        return value.dump(context, validate_on_dump=False)

    @unserialize_super()
    def unserialize(self, value, context, data):
        try:
            return self.document_type().load(value, context, validate_on_load=False)
        except:
            return None

    @validate_super
    def validate(self, value):
        return isinstance(value, self.document_type)


class FloatField(Field):

    @serialize_super()
    def serialize(self, value, context, obj):
        return value

    @unserialize_super()
    def unserialize(self, value, context, data):
        if not isinstance(value, (float, int, long)):
            return None
        else:
            return float(value)

    @validate_super
    def validate(self, value):
        return isinstance(value, float)


class IntField(Field):

    @serialize_super()
    def serialize(self, value, context, obj):
        return value

    @unserialize_super()
    def unserialize(self, value, context, data):
        if not isinstance(value, int):
            return None
        else:
            return value

    @validate_super
    def validate(self, value):
        return isinstance(value, int)


class ListField(Field):

    def __init__(self, field_type, *args, **kwargs):
        self.field_type = field_type
        self.field_type.required = True  # don't allow Nones in list
        super(ListField, self).__init__(*args, **kwargs)

    @serialize_super(none_value=list)
    def serialize(self, value, context, obj):
        return [self.field_type.serialize(v, context, obj) for v in value]

    @unserialize_super(none_value=list)
    def unserialize(self, value, context, data):
        if not isinstance(value, collections.Iterable):
            return []
        return [self.field_type.unserialize(v, context, data) for v in value]

    @validate_super
    def validate(self, value):
        if not isinstance(value, list):
            return False

        for v in value:
            if not self.field_type.validate(v):
                return False

        return True


class ObjectIDField(Field):

    @serialize_super()
    def serialize(self, value, context, obj):
        if context == 'db':
            return value
        elif context == 'web':
            return str(value)

    @unserialize_super()
    def unserialize(self, value, context, data):
        if context == 'db':
            return value
        elif context == 'web':
            try:
                return ObjectId(value)
            except InvalidId:
                # TODO: log this error
                return None

    @validate_super
    def validate(self, value):
        return isinstance(value, ObjectId)


class StringField(Field):

    @serialize_super()
    def serialize(self, value, context, obj):
        if isinstance(value, unicode):
            # TODO: figure out a better Unicode strategy
            return value.encode('ascii', 'ignore')
        elif isinstance(value, str):
            return value
        else:
            return None

    @unserialize_super()
    def unserialize(self, value, context, data):
        if isinstance(value, unicode):
            return value.encode('ascii', 'ignore')
        elif isinstance(value, str):
            return value
        else:
            return None

    @validate_super
    def validate(self, value):
        return isinstance(value, (str, unicode))

# Field validators


def validate_choices(choices):
    return (lambda x: x in choices)

# Documents


class Document(object):
    fields = []

    def __init__(self, **kwargs):
        for field_name, field in self.fields:
            field_value = kwargs.get(field_name)
            if field_value is None:
                self.__setattr__(field_name, field.default)
            else:
                self.__setattr__(field_name, kwargs.get(field_name))

        self.post_init()

    def __repr__(self):
        field_strs = []
        for field_name, field in self.fields:
            field_value = self.__getattribute__(field_name)
            field_strs.append("{}: {}".format(field_name, field_value))
        return '{{{}}}'.format(', '.join(field_strs))

    def __str__(self):
        return repr(self)

    def __eq__(self, other):
        if other is None:
            return False
        return all([self.__getattribute__(field_name) == other.__getattribute__(field_name)
                    for field_name, _ in self.fields])

    def __ne__(self, other):
        return not self == other

    def dump(self, context=None, exclude=None, only=None, validate_on_dump=True):
        return_dict = {}

        if validate_on_dump and not self.validate():
            is_valid, errors = self.validate()
            if not is_valid:
                raise ValidationError(str(errors))

        for field_name, field in self.fields:
            if exclude is not None and field_name in exclude:
                continue
            if only is not None and field_name not in only:
                continue

            field_value = self.__getattribute__(field_name)

            to_name = field_name
            if field.dump_to is not None:
                if isinstance(field.dump_to, dict):
                    to_name = field.dump_to.get(context, field_name)
                elif isinstance(field.dump_to, str):
                    to_name = field.dump_to

            return_dict[to_name] = field.serialize(field_value, context, self)

        return return_dict

    @classmethod
    def load(cls, data, context=None, validate_on_load=True, strict=False):
        if not isinstance(data, dict):
            if strict:
                raise ValidationError("can only load data from dicts")
            return None

        init_args = dict()
        for field_name, field in cls.fields:
            from_name = field_name
            if field.load_from is not None:
                if isinstance(field.load_from, dict):
                    from_name = field.load_from.get(context, field_name)
                elif isinstance(field.load_from, str):
                    from_name = field.load_from

            field_value = field.unserialize(data.get(from_name), context, data)
            if field_value is None:
                init_args[field_name] = field.default
            else:
                init_args[field_name] = field_value

        return_document = cls(**init_args)

        if validate_on_load and not return_document.validate():
            if strict:
                raise ValidationError
            return None

        return return_document

    def validate(self):
        if not self.validate_document():
            return False, 'validate_document'

        for field_name, field in self.fields:
            field_value = self.__getattribute__(field_name)
            if not field.validate(field_value):
                return False, 'validate_field ({})'.format(field_name)

        return True, None

    # override to do something (i.e. initialize properties) post-init/load
    def post_init(self):
        pass

    # override for document-wide validation
    def validate_document(self):
        return True

# Embedded documents


class AliasMapping(Document):
    fields = [('player_id', ObjectIDField()),
              ('player_alias', StringField(required=True))]


class AliasMatch(Document):
    fields = [('winner', StringField(required=True)),
              ('loser', StringField(required=True))]


class Match(Document):
    fields = [('winner', ObjectIDField(required=True)),
              ('loser', ObjectIDField(required=True))]

    def __str__(self):
        return "%s > %s" % (self.winner, self.loser)

    def contains_players(self, player1, player2):
        return (self.winner == player1 and self.loser == player2) or \
               (self.winner == player2 and self.loser == player1)

    def contains_player(self, player_id):
        return self.winner == player_id or self.loser == player_id

    def did_player_win(self, player_id):
        return self.winner == player_id

    def get_opposing_player_id(self, player_id):
        if self.winner == player_id:
            return self.loser
        elif self.loser == player_id:
            return self.winner
        else:
            return None


class RankingEntry(Document):
    fields = [('player', ObjectIDField(required=True)),
              ('rank', IntField(required=True)),
              ('rating', FloatField(required=True))]


class Rating(Document):
    fields = [('mu', FloatField(required=True, default=25.)),
              ('sigma', FloatField(required=True, default=25. / 3))]

    def trueskill_rating(self):
        return trueskill.Rating(mu=self.mu, sigma=self.sigma)

    @classmethod
    def from_trueskill(cls, trueskill_rating):
        return Rating(mu=trueskill_rating.mu,
                      sigma=trueskill_rating.sigma)


# MongoDB collection documents

MONGO_ID_SELECTOR = {'db': '_id',
                     'web': 'id'}


class Player(Document):
    fields = [('id', ObjectIDField(required=True, load_from=MONGO_ID_SELECTOR,
                                   dump_to=MONGO_ID_SELECTOR)),
              ('name', StringField(required=True)),
              ('aliases', ListField(StringField())),
              ('ratings', DictField(StringField(), DocumentField(Rating))),
              ('regions', ListField(StringField())),
              ('merged', BooleanField(required=True, default=False)),
              ('merge_parent', ObjectIDField()),
              ('merge_children', ListField(ObjectIDField()))
              ]

    def post_init(self):
        # initialize merge_children to contain id if it does not already
        if not self.merge_children:
            self.merge_children = [self.id]

    @classmethod
    def create_with_default_values(cls, name, region):
        return cls(id=ObjectId(),
                   name=name,
                   aliases=[name.lower()],
                   ratings={},
                   regions=[region])


class Tournament(Document):
    fields = [('id', ObjectIDField(required=True, load_from=MONGO_ID_SELECTOR,
                                   dump_to=MONGO_ID_SELECTOR)),
              ('name', StringField(required=True)),
              ('type', StringField(
                  required=True,
                  validators=[validate_choices(SOURCE_TYPE_CHOICES)])),
              ('date', DateTimeField()),
              ('regions', ListField(StringField())),
              ('url', StringField()),
              ('raw', StringField()),
              ('matches', ListField(DocumentField(Match))),
              ('players', ListField(ObjectIDField())),
              ('orig_ids', ListField(ObjectIDField()))]

    def replace_player(self, player_to_remove=None, player_to_add=None):
        # TODO edge cases with this
        # TODO the player being added cannot play himself in any match
        if player_to_remove is None or player_to_add is None:
            raise TypeError(
                "player_to_remove and player_to_add cannot be None!")

        player_to_remove_id = player_to_remove.id
        player_to_add_id = player_to_add.id

        if player_to_remove_id not in self.players:
            print "Player with id %s is not in this tournament. Ignoring." % player_to_remove.id
            return

        self.players.remove(player_to_remove_id)
        self.players.append(player_to_add_id)

        for match in self.matches:
            if match.winner == player_to_remove_id:
                match.winner = player_to_add_id

            if match.loser == player_to_remove_id:
                match.loser = player_to_add_id

    @classmethod
    def from_pending_tournament(cls, pending_tournament):
        # takes a real alias to id map instead of a list of objects
        def _get_player_id_from_map_or_throw(alias_to_id_map, alias):
            if alias in alias_to_id_map:
                return alias_to_id_map[alias]
            else:
                raise ValueError('Alias %s has no ID in map\n: %s' %
                                 (alias, alias_to_id_map))

        alias_to_id_map = dict([(entry.player_alias, entry.player_id)
                                for entry in pending_tournament.alias_to_id_map
                                if entry.player_id is not None])

        # we need to convert pending tournament players/matches to player IDs
        print pending_tournament.players, pending_tournament.matches
        players = [_get_player_id_from_map_or_throw(
            alias_to_id_map, p) for p in pending_tournament.players]
        matches = []
        for am in pending_tournament.matches:
            m = Match(
                winner=_get_player_id_from_map_or_throw(
                    alias_to_id_map, am.winner),
                loser=_get_player_id_from_map_or_throw(
                    alias_to_id_map, am.loser)
            )
            matches.append(m)
        return cls(
            id=pending_tournament.id,
            name=pending_tournament.name,
            type=pending_tournament.type,
            date=pending_tournament.date,
            regions=pending_tournament.regions,
            url=pending_tournament.url,
            raw=pending_tournament.raw,
            matches=matches,
            players=players,
            orig_ids=players)


class PendingTournament(Document):
    fields = [('id', ObjectIDField(required=True, load_from=MONGO_ID_SELECTOR,
                                   dump_to=MONGO_ID_SELECTOR)),
              ('name', StringField(required=True)),
              ('type', StringField(required=True)),
              ('date', DateTimeField()),
              ('regions', ListField(StringField())),
              ('url', StringField()),
              ('raw', StringField()),
              ('matches', ListField(DocumentField(AliasMatch))),
              ('players', ListField(StringField())),
              ('alias_to_id_map', ListField(DocumentField(AliasMapping)))]

    def set_alias_id_mapping(self, alias, id):
        if self.alias_to_id_map is None:
            self.alias_to_id_map = []

        for mapping in self.alias_to_id_map:
            if mapping.player_alias == alias:
                mapping.player_alias = alias
                mapping.player_id = id
                return

        # if we've gotten out here, we couldn't find an existing match, so add
        # a new element
        self.alias_to_id_map.append(AliasMapping(
            player_alias=alias,
            player_id=id
        ))

    def delete_alias_id_mapping(self, alias):
        if self.alias_to_id_map is None:
            self.alias_to_id_map = []

        for mapping in self.alias_to_id_map:
            if mapping.player_alias == alias:
                self.alias_to_id_map.remove(mapping)
                return mapping

    @classmethod
    def from_scraper(cls, type, scraper, region_id):
        regions = [region_id]
        return cls(
            id=ObjectId(),
            name=scraper.get_name(),
            type=type,
            date=scraper.get_date(),
            regions=regions,
            url=scraper.get_url(),
            raw=scraper.get_raw(),
            players=scraper.get_players(),
            matches=scraper.get_matches())


class Ranking(Document):
    fields = [('id', ObjectIDField(required=True, load_from=MONGO_ID_SELECTOR,
                                   dump_to=MONGO_ID_SELECTOR)),
              ('region', StringField(required=True)),
              ('tournaments', ListField(ObjectIDField())),
              ('time', DateTimeField()),
              ('ranking', ListField(DocumentField(RankingEntry)))]


class Region(Document):
    fields = [('id', StringField(required=True, load_from=MONGO_ID_SELECTOR,
                                 dump_to=MONGO_ID_SELECTOR)),
              ('display_name', StringField(required=True))]


class User(Document):
    fields = [('id', StringField(required=True, load_from=MONGO_ID_SELECTOR,
                                 dump_to=MONGO_ID_SELECTOR)),
              ('username', StringField(required=True)),
              ('salt', StringField(required=True)),
              ('hashed_password', StringField(required=True)),
              ('admin_regions', ListField(StringField()))]


class Merge(Document):
    fields = [('id', ObjectIDField(required=True, load_from=MONGO_ID_SELECTOR,
                                   dump_to=MONGO_ID_SELECTOR)),
              ('requester_user_id', StringField(required=True)),
              ('source_player_obj_id', ObjectIDField(required=True)),
              ('target_player_obj_id', ObjectIDField(required=True)),
              ('time', DateTimeField())]


class Session(Document):
    fields = [('session_id', StringField(required=True)),
              ('user_id', StringField(required=True))]
