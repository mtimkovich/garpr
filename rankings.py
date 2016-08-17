from datetime import datetime, timedelta
from model import *
import rating_calculators
import trueskill

def generate_ranking(dao, now=datetime.now(), day_limit=60, num_tourneys=2):
    player_date_map = {}
    player_set = set()

    tournaments = dao.get_all_tournaments(regions=[dao.region])
    for tournament in tournaments:
        print 'Processing:', tournament.name.encode('utf-8')

        for player in tournament.players:
            player_date_map[player.id] = tournament.date

        for match in tournament.matches:
            if not match.winner in player_set:
                match.winner.update_rating(Rating.from_trueskill(dao.region, trueskill.Rating()))
                player_set.add(match.winner)

            if not match.loser in player_set:
                match.loser.update_rating(Rating.from_trueskill(dao.region, trueskill.Rating()))
                player_set.add(match.loser)

            rating_calculators.update_trueskill_ratings(dao.region, winner=match.winner, loser=match.loser)

    print 'Checking for player inactivity...'

    players = list(player_set)
    sorted_players = sorted(
            players,
            key=lambda player: trueskill.expose(player.get_rating(dao.region).trueskill_rating()), reverse=True)

    rank = 1
    ranking = []
    for player in sorted_players:
        player_last_active_date = player_date_map.get(player.id)
        if player_last_active_date is None or dao.is_inactive(player, now, day_limit, num_tourneys) or not dao.region in player.regions:
            pass # do nothing, skip this player
        else:
            ranking.append(RankingEntry(
                rank=rank,
                player=player,
                rating=player.get_rating(dao.region)
                ))
            rank += 1

    print 'Updating players...'
    for i, p in enumerate(players, start=1):
        p.save()
        # print 'Updated player %d of %d' % (i, len(players))

    print 'Inserting new ranking...'
    ranking = Ranking(
        region=dao.region,
        time=now,
        rankings=ranking,
        tournaments=tournaments)
    ranking.save()

    print 'Done!'
