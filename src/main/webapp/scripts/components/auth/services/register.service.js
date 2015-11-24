'use strict';

angular.module('vtoolsApp')
    .factory('Register', function ($resource) {
        return $resource('api/register', {}, {
        });
    });


