import trueskill
from model import Rating


def update_trueskill_ratings(region, winner=None, loser=None):
    new_winner_rating, new_loser_rating = trueskill.rate_1vs1(
        winner.get_rating(region).trueskill_rating(),
        loser.get_rating(region).trueskill_rating()
    )

    winner.update_rating(Rating.from_trueskill(region, new_winner_rating))
    loser.update_rating(Rating.from_trueskill(region, new_loser_rating))
