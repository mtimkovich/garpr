angular.module('app.players')
  .controller("PlayerTypeaheadController", function($scope, RegionService, PlayerService) {
    $scope.regionService = RegionService;
    $scope.playerService = PlayerService;
  });

