angular.module('app.players')
  .controller("PlayerTypeaheadController", function($scope, PlayerService) {
    $scope.playerService = PlayerService;
  });

