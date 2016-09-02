from mongoengine import Document,                  \
    EmbeddedDocument,          \
    BooleanField,              \
    DateTimeField,             \
    EmbeddedDocumentField,     \
    EmbeddedDocumentListField, \
    FloatField,                \
    IntField,                  \
    ListField,                 \
    ReferenceField,            \
    StringField,               \
    ValidationError
import trueskill

SOURCE_TYPE_CHOICES = ('tio', 'challonge', 'smashgg', 'other')

# MongoEngine embedded documents (i.e. subobjects of other documents)


class AliasMapping(EmbeddedDocument):
    player_alias = StringField(required=True)
    player = ReferenceField('Player')

    def __str__(self):
        return '{}: {}'.format(self.player_alias, self.player)


class AliasMatch(EmbeddedDocument):
    # TODO: should these be indices into aliases?
    winner = StringField(required=True)
    loser = StringField(required=True)

    def __str__(self):
        return '{} > {}'.format(self.winner, self.loser)


class Match(EmbeddedDocument):
    winner = ReferenceField('Player', required=True)
    loser = ReferenceField('Player', required=True)

    def __str__(self):
        return '{} > {}'.format(self.winner, self.loser)

    def contains_players(self, p1_id, p2_id):
        return {self.winner.id, self.loser.id} == {p1_id, p2_id}

    def contains_player(self, player_id):
        return player_id in [self.winner.id, self.loser.id]

    def did_player_win(self, player_id):
        return self.winner.id == player_id

    def get_opposing_player(self, player_id):
        if self.winner.id == player_id:
            return self.loser
        elif self.loser.id == player_id:
            return self.winner
        else:
            return None

    def replace_player(self, player_to_remove, player_to_add):
        if self.winner == player_to_remove:
            self.winner = player_to_add
        if self.loser == player_to_remove:
            self.loser = player_to_add


class RankingEntry(EmbeddedDocument):
    rank = IntField(required=True, min_value=1)
    player = ReferenceField('Player', required=True)
    rating = EmbeddedDocumentField('Rating')

    def __str__(self):
        return "{}. {}".format(self.rank, self.player)


class Rating(EmbeddedDocument):
    region = ReferenceField('Region', required=True)
    mu = FloatField(required=True)
    sigma = FloatField(required=True, default=0.)

    def __str__(self):
        return "(mu={:.2f},sigma={:.2f})".format(self.mu, self.sigma)

    def trueskill_rating(self):
        return trueskill.Rating(mu=self.mu, sigma=self.sigma)

    @classmethod
    def from_trueskill(cls, region, trueskill_rating):
        return Rating(region=region,
                      mu=trueskill_rating.mu,
                      sigma=trueskill_rating.sigma)

# MongoEngine documents (i.e. collections in Mongo)


class Merge(Document):
    requester = ReferenceField('User', required=True)
    source_player = ReferenceField('Player', required=True)
    target_player = ReferenceField('Player', required=True)
    time = DateTimeField(required=True)

    def clean(self):
        source = self.source_player
        target = self.target_player

        # check: source and target different players
        if source == target:
            raise ValidationError("source and target must be different")

        # check: source and target not already merged
        if source.merged:
            raise ValidationError("source is already merged")

        if target.merged:
            raise ValidationError("target is already merged")

        # # check: source not in target merge_children or vice versa
        # # (this should never happen)
        # if (source in target.merge_children) or (target in source.merge_children):
        #     raise ValidationError("source and target already merged")

        # check: source and target have never played in same tournament
        # (can't merge players who've played each other)
        # TODO: reduce db calls for this
        for tournament in Tournament.objects.exclude('raw'):
            if source in tournament.players and target in tournament.players:
                raise ValidationError(
                    "source and target have played in same tournament")

    def __str__(self):
        return "{} merged into {}".format(self.source_player, self.target_player)


class Player(Document):
    name = StringField(required=True)
    aliases = ListField(StringField())
    ratings = EmbeddedDocumentListField('Rating')
    regions = ListField(ReferenceField('Region'))

    merged = BooleanField(required=True, default=False)
    merge_parent = ReferenceField('Player')
    merge_children = ListField(ReferenceField('Player'))

    def clean(self):
        # check: merged is True <=> merge_parent not None
        if self.merged and self.merge_parent is None:
            raise ValidationError("player is merged but has no parent")

        if self.merge_parent and not self.merged:
            raise ValidationError("player has merge_parent but is not merged")

        # clean: if aliases empty add name to aliases
        if len(self.aliases) == 0:
            self.aliases.append(self.name.lower())

    # TODO: add back other properties to this?
    def __str__(self):
        return "{} ({})".format(self.name, self.id)

    def get_rating(self, region):
        return self.ratings.filter(region=region).first()

    def update_rating(self, rating):
        self.delete_rating(rating.region)
        self.ratings.append(rating)

    def delete_rating(self, region):
        self.ratings.filter(region=region).delete()


class Region(Document):
    id = StringField(required=True, unique=True, primary_key=True)
    display_name = StringField(required=True)

    def __str__(self):
        return "{} ({})".format(self.display_name, self.id)


class Ranking(Document):
    region = ReferenceField('Region', required=True)
    time = DateTimeField(required=True)
    rankings = EmbeddedDocumentListField('RankingEntry')
    tournaments = ListField(ReferenceField('Tournament'))

    def __str__(self):
        return ";".join(str(ranking) for ranking in self.rankings)


class Session(Document):
    id = StringField(required=True, unique=True, primary_key=True)
    user = ReferenceField('User', required=True, unique=True)

    def __str__(self):
        return "{} ({})".format(self.id, self.user)


class BaseTournament(Document):
    name = StringField(required=True)
    source_type = StringField(choices=SOURCE_TYPE_CHOICES,
                              required=True)
    date = DateTimeField(required=True)
    regions = ListField(ReferenceField('Region'))
    raw = StringField()

    meta = {'abstract': True}

    def __str__(self):
        return "{} ({})".format(self.name, self.date.date().isoformat())


class Tournament(BaseTournament):
    players = ListField(ReferenceField('Player'), required=True)
    matches = EmbeddedDocumentListField('Match', required=True)
    orig_ids = ListField(ReferenceField('Player'), required=True)

    def clean(self):
        # check: set of players in players = set of players in matches
        players_ids = {player.id for player in self.players}
        matches_ids = {match.winner.id for match in self.matches} | \
                      {match.loser.id for match in self.matches}

        if players_ids != matches_ids:
            raise ValidationError(
                "set of players in players differs from set of players in matches")

        # check: no one plays themselves
        for match in self.matches:
            if match.winner.id == match.loser.id:
                raise ValidationError(
                    "tournament contains match where player plays themself")

        # check: no merged players in player list
        for player in self.players:
            if player.merged:
                raise ValidationError("player in tournament has been merged")

        # clean: if adding for first time with empty orig_ids, set equal to
        # players
        if len(self.orig_ids) == 0:
            self.orig_ids = [player for player in self.players]

        # check: len of orig_ids should equal len of players
        if len(self.orig_ids) != len(self.players):
            raise ValidationError("different number of orig_ids and players")

    # replaces player in tournament with other player (used for merging)
    # does not save; you must save after calling this
    def replace_player(self, player_to_remove, player_to_add):
        if player_to_remove is None or player_to_add is None:
            raise TypeError("cannot replace a None player")
        if player_to_remove in self.players:
            self.players.remove(player_to_remove)
            self.players.append(player_to_add)
        for match in self.matches:
            match.replace_player(player_to_remove, player_to_add)

    @classmethod
    def from_pending_tournament(cls, pending_tournament):
        tournament = Tournament()
        tournament.name = pending_tournament.name
        tournament.source_type = pending_tournament.source_type
        tournament.date = pending_tournament.date
        tournament.regions = pending_tournament.regions
        tournament.raw = pending_tournament.raw

        alias_to_id_map = {mapping.player_alias: mapping.player
                           for mapping in pending_tournament.alias_mappings}
        for alias in pending_tournament.aliases:
            if alias not in alias_to_id_map:
                raise ValueError('Alias {} has no ID in map'.format(alias))

        tournament.players = [alias_to_id_map[alias]
                              for alias in pending_tournament.aliases]
        tournament.orig_ids = [p for p in tournament.players]
        tournament.matches = [Match(winner=alias_to_id_map[alias_match.winner],
                                    loser=alias_to_id_map[alias_match.loser])
                              for alias_match in pending_tournament.alias_matches]

        return tournament


class PendingTournament(BaseTournament):
    # players in old PendingTournament
    aliases = ListField(StringField(), required=True)
    alias_mappings = EmbeddedDocumentListField('AliasMapping')
    alias_matches = EmbeddedDocumentListField('AliasMatch', required=True)

    def clean(self):
        # check: set of aliases = set of aliases in matches
        set_aliases = set(self.aliases)
        matches_aliases = {match.winner for match in self.alias_matches} | \
                          {match.loser for match in self.alias_matches}
        mapping_aliases = {
            mapping.player_alias for mapping in self.alias_mappings}

        if set_aliases != matches_aliases:
            raise ValidationError(
                "set of players in players differs from set of players in matches")

        # check: set of aliases in mapping is subset of aliases
        if not mapping_aliases.issubset(set_aliases):
            raise ValidationError(
                "alias mappings contains mapping for alias not in tournament")

    def set_alias_mapping(self, alias, player):
        for mapping in self.alias_mappings:
            if mapping.player_alias == alias:
                mapping.player = player
                return

        # no existing mapping, add new element
        mapping = AliasMapping(player_alias=alias, player=player)
        self.alias_mappings.append(mapping)

    def delete_alias_mapping(self, alias):
        self.alias_mappings.filter(player_alias=alias).delete()

    @classmethod
    def from_scraper(cls, source_type, scraper, regions):
        tournament = PendingTournament()
        tournament.name = scraper.get_name()
        tournament.source_type = source_type
        tournament.date = scraper.get_date()
        tournament.regions = regions
        tournament.raw = str(scraper.get_raw())
        tournament.aliases = scraper.get_players()
        for match in scraper.get_matches():
            alias_match = AliasMatch(winner=match['winner'],
                                     loser=match['loser'])
            tournament.alias_matches.append(alias_match)
        return tournament


class User(Document):
    username = StringField(required=True, unique=True, primary_key=True)
    salt = StringField(required=True)
    hashed_password = StringField(required=True)

    admin_regions = ListField(ReferenceField('Region'))

    def __str__(self):
        return self.username
