angular.module('app.players')
  .directive('playerTypeaheadDirective', function() {
    return {
      templateUrl: "app/players/views/player_typeahead.html",
      controller: "PlayerTypeaheadController",
      // transclude: true,
      scope: {
        typeaheadClass: "@",
        player: "=",
        placeholder: "@",
        onPlayerSelect: "&"
      },
    }
  });

