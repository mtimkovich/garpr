angular.module('app.rankings').service('RankingsService', function($http, SessionService) {
    var service = {
        rankingsList: null,
        calculateDaysSince: function(startDate){
            var oneDay = 24*60*60*1000;
            var nowDate = new Date();
            return Math.round(Math.abs((startDate.getTime() - nowDate.getTime())/(oneDay)));
        }
    };
    return service;
});