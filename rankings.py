from datetime import datetime

import trueskill

import model as M
import rating_calculators


def generate_ranking(dao, now=datetime.now(), day_limit=60, num_tourneys=2):
    player_date_map = {}
    player_set = set()

    tournaments = dao.get_all_tournaments(regions=[dao.region])
    for tournament in tournaments:
        print 'Processing:', tournament.name.encode('utf-8')

        for player in tournament.players:
            player_date_map[player.id] = tournament.date

        for match in tournament.matches:
            if match.winner not in player_set:
                match.winner.update_rating(
                    M.Rating.from_trueskill(dao.region, trueskill.Rating()))
                player_set.add(match.winner)

            if match.loser not in player_set:
                match.loser.update_rating(
                    M.Rating.from_trueskill(dao.region, trueskill.Rating()))
                player_set.add(match.loser)

            # print 'BEFORE:'
            # print '--------------------'
            # print 'Winner:', match.winner.name, match.winner.get_rating(dao.region)
            # print 'Loser:', match.loser.name, match.loser.get_rating(dao.region)
            # # for p in player_set:
            # #     print p.name, p.get_rating(dao.region)
            # print '--------------------'

            rating_calculators.update_trueskill_ratings(
                dao.region, winner=match.winner, loser=match.loser)

            # print 'AFTER:'
            # print '--------------------'
            # print 'Winner:', match.winner.name, match.winner.get_rating(dao.region)
            # print 'Loser:', match.loser.name, match.loser.get_rating(dao.region)
            # print '--------------------'

    print 'Checking for player inactivity...'

    players = list(player_set)

    # reload from mongoengine
    # TODO: fix to reduce number of queries
    for p in players:
        p.reload()

    sorted_players = sorted(
        players,
        key=lambda player: trueskill.expose(player.get_rating(dao.region).trueskill_rating()), reverse=True)

    print sorted_players

    rank = 1
    ranking = []
    for player in sorted_players:
        player_last_active_date = player_date_map.get(player.id)
        if player_last_active_date is None or \
                dao.is_inactive(player, now, day_limit, num_tourneys) or \
                dao.region not in player.regions:
            pass  # do nothing, skip this player
        else:
            ranking.append(M.RankingEntry(
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
    ranking = M.Ranking(
        region=dao.region,
        time=now,
        rankings=ranking,
        tournaments=tournaments)
    ranking.save()

    print 'Done!'
