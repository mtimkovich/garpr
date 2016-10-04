var app = angular.module('app', ['ngRoute', 'ui.bootstrap', 'angulartics', 'angulartics.google.analytics', 'facebook']);






app.config(function ($httpProvider) {
    $httpProvider.defaults.withCredentials = true;
    $httpProvider.defaults.useXDomain = true;
    $httpProvider.defaults.headers.common = 'Content-Type: application/json';
    delete $httpProvider.defaults.headers.common['X-Requested-With'];
    //rest of route code
});

app.config(['$routeProvider', function($routeProvider) {
    $routeProvider.when('/:region/rankings', {
        templateUrl: 'rankings/views/rankings.html',
        controller: 'RankingsController',
        activeTab: 'rankings'
    }).
    when('/:region/players', {
        templateUrl: 'players/views/players.html',
        controller: 'PlayersController',
        activeTab: 'players'
    }).
    when('/:region/players/:playerId', {
        templateUrl: 'players/views/player_detail.html',
        controller: 'PlayerDetailController',
        activeTab: 'players'
    }).
    when('/:region/tournaments', {
        templateUrl: 'tournaments/views/tournaments.html',
        controller: 'TournamentsController',
        activeTab: 'tournaments'
    }).
    when('/:region/tournaments/:tournamentId', {
        templateUrl: 'tournaments/views/tournament_detail.html',
        controller: 'TournamentDetailController',
        activeTab: 'tournaments'
    }).
    when('/:region/merges', {
        templateUrl: 'players/views/merges.html',
        controller: 'MergesController',
        activeTab: 'tournaments'
    }).
    when('/:region/headtohead', {
        templateUrl: 'head_to_head/views/headtohead.html',
        controller: 'HeadToHeadController',
        activeTab: 'headtohead'
    }).
    when('/:region/seed', {
        templateUrl: 'tools/seed_tournament/seed.html',
        controller: 'SeedController',
        activeTab: 'seed'
    }).
    when('/about', {
        templateUrl: 'common/about/about.html',
        activeTab: 'about'
    }).
    when('/adminfunctions',{
        templateUrl: 'tools/admin_functions/admin_functions.html',
        controller: 'AdminFunctionsController'
    }).
    otherwise({
        redirectTo: '/' + defaultRegion + '/rankings'
    });
}]);




