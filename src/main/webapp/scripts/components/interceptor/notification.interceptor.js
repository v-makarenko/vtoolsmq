 'use strict';

angular.module('vtoolsApp')
    .factory('notificationInterceptor', function ($q, AlertService) {
        return {
            response: function(response) {
                var alertKey = response.headers('X-vtoolsApp-alert');
                if (angular.isString(alertKey)) {
                    AlertService.success(alertKey, { param : response.headers('X-vtoolsApp-params')});
                }
                return response;
            }
        };
    });
