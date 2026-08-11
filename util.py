import csv

class Util:

    @staticmethod
    def read_games(file):
        """ Initializes game objects from csv """
        games = [item for item in csv.DictReader(open(file))]

        for game in games:
            game['season'], game['neutral'], game['playoff'] = int(game['season']), int(game['neutral']), int(game['playoff'])
            game['score1'], game['score2'] = int(game['score1']) if game['score1'] != '' else None, int(game['score2']) if game['score2'] != '' else None
            game['elo_prob1'], game['result1'] = float(game['elo_prob1']) if game['elo_prob1'] != '' else None, float(game['result1']) if game['result1'] != '' else None

        return games

    @staticmethod
    def score_probability(prob, result, playoff):
        """ Scores a rounded win probability against the actual result using the game's point system """
        rounded_prob = round(prob, 2)
        brier = (rounded_prob - result) * (rounded_prob - result)
        points = 25 - (100 * brier)
        points = round(points + 0.001 if points < 0 else points, 1) # Round half up
        if playoff == 1:
            points *= 2
        return points

    @staticmethod
    def evaluate_forecasts(games):
        """ Evaluates and scores forecasts in the my_prob1 field against those in the elo_prob1 field for each game """
        my_points_by_season, elo_points_by_season = {}, {}

        forecasted_games = [g for g in games if g['result1'] != None]
        upcoming_games = [g for g in games if g['result1'] == None and 'my_prob1' in g]

        # Evaluate forecasts and group by season
        for game in forecasted_games:

            # Skip unplayed games, ties, and games with no benchmark to compare against
            if game['result1'] == None or game['result1'] == 0.5 or game['elo_prob1'] == None:
                continue

            if game['season'] not in elo_points_by_season:
                elo_points_by_season[game['season']] = 0.0
                my_points_by_season[game['season']] = 0.0

            elo_points_by_season[game['season']] += Util.score_probability(game['elo_prob1'], game['result1'], game['playoff'])
            my_points_by_season[game['season']] += Util.score_probability(game['my_prob1'], game['result1'], game['playoff'])

        # Print individual seasons
        for season in my_points_by_season:
            print("In %s, your forecasts would have gotten %s points. Elo got %s points." % (season, round(my_points_by_season[season], 2), round(elo_points_by_season[season], 2)))

        # Show overall performance
        my_avg = sum(my_points_by_season.values())/len(my_points_by_season.values())
        elo_avg = sum(elo_points_by_season.values())/len(elo_points_by_season.values())
        print("\nOn average, your forecasts would have gotten %s points per season. Elo got %s points per season.\n" % (round(my_avg, 2), round(elo_avg, 2)))

        # Print forecasts for upcoming games
        if len(upcoming_games) > 0:
            print("Forecasts for upcoming games:")
            for game in upcoming_games:
                elo_display = "%s%%" % int(round(100*game['elo_prob1'])) if game['elo_prob1'] != None else "N/A"
                print("%s\t%s vs. %s\t\t%s (Elo)\t\t%s%% (You)" % (game['date'], game['team1'], game['team2'], elo_display, int(round(100*game['my_prob1']))))
            print("")
