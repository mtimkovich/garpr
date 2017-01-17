angular.module('app.headToHead').controller("HeadToHeadController", function($scope, $http, $routeParams, RegionService, PlayerService) {
    RegionService.setRegion($routeParams.region);
    $scope.regionService = RegionService;
    $scope.playerService = PlayerService;
    $scope.player1 = null;
    $scope.player2 = null;
    $scope.wins = 0;
    $scope.losses = 0;

    // get fresh "player" from the change listener, since the model updates after the change listener is fired...
    $scope.onPlayer1Change = function(player) {
      $scope.player1 = player;
      onChange();
    }

    $scope.onPlayer2Change = function(player) {
      $scope.player2 = player;
      onChange();
    }

    onChange = function() {
        if ($scope.player1 != null && $scope.player2 != null) {
            $http.get(hostname + $routeParams.region +
                '/matches/' + $scope.player1.id + '?opponent=' + $scope.player2.id).
                success(function(data) {
                    $scope.playerName = $scope.player1.name;
                    $scope.opponentName = $scope.player2.name;
                    $scope.matches = data.matches.reverse();
                    $scope.wins = data.wins;
                    $scope.losses = data.losses;
                });
        }
    };

    $scope.determineMatchStatus = function(match, playerName, opponentName){
        var status = '';
        status = match.result == 'win' ? playerName : opponentName;
        if(match.result === 'excluded')
            status = 'MATCH EXCLUDED';
        return status;
    }
});
