// Add endsWith to String prototype
String.prototype.endsWith = function(suffix) {
    return this.indexOf(suffix, this.length - suffix.length) !== -1;
};
var _promises = [];
var promise_success = function(uid, result) {
	if (_promises[uid] == undefined || _promises[uid]._success_callback == undefined) {
		return;
	}
	_promises[uid]._success_callback(result);
	delete _promises[uid];
}
var promise_error = function(uid, err) {
	if (_promises[uid] == undefined || _promises[uid]._error_callback == undefined) {
		return;
	}
	_promises[uid]._error_callback(err);
	delete _promises[uid];
}
var when = function(result) {
	return {
		then: function(callback, error_callback) {
			if (result && result['_promise_success'] !== undefined && result['_promise_error'] !== undefined) {
				var uid = result['_promise_uid']();
				if (_promises[uid] == undefined) {
					_promises[uid] = self
				}
				_promises[uid]._success_callback = callback;
				_promises[uid]._error_callback = error_callback;
				result._promise_success.connect(promise_success);
				result._promise_error.connect(promise_error);
				result.start();
			} else {
				callback(result);
			}
		}
	};
}
function drive_module(name) {
	var app = angular.module(name, ['pascalprecht.translate']);
	app.directive('driveInclude', function($http, $templateCache, $compile) {
	    return function(scope, element, attrs) {
	        $http.get(scope.getTemplate(attrs.driveInclude), { cache: $templateCache }).success(
	        function(response) {
	            var contents = element.html(response).contents();
	            $compile(contents)(scope);
	        });
	    };
	});
	app.config(function ($translateProvider) {
		var languages = angular.fromJson(drive.get_translations());
		for (var i=0; i<languages.length; i++) {
			$translateProvider.translations(languages[i][0], languages[i][1]);
		}
		$translateProvider.preferredLanguage(drive.locale());
	});
	app.run(function() {
		$("body").css('visibility', 'visible');
	});
	return app;
}
var tracker = drive.get_tracker_id();
if (tracker != "") {
	(function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
	(i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
	m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
	})(window,document,'script','https://www.google-analytics.com/analytics.js','ga');

	ga('create', tracker, 'auto');
	ga('send', 'pageview');
}

// Default controller
var DriveController = function($scope, $translate) {
	// Map default drive API
	self = this;
	$scope.currentAction = "";
	$scope.engines = this.getEngines();
	$scope.need_adv_menu = this.needAdvMenu;
	$scope.is_paused = this.isPaused;
	$scope.suspend = this.suspendEngines;
	$scope.resume = this.resumeEngines;
	$scope.open_remote = this.openRemote;
	$scope.open_local = this.openLocal;
	$scope.app_update = this.appUpdate;
	$scope.auto_update = this.getAutoUpdate();
	$scope.get_update_status = this.getUpdateStatus;
	$scope.show_conflicts = this.showConflicts;
	$scope.update_password = function(uid, password) {
		$scope.update_password_error = "CONNECTING";
		self.updatePassword($scope, uid, password);
	}
	$scope.version = drive.get_version();
	$scope.update_url = drive.get_update_url();
	$scope.quit = this.quit;
	$scope.show_settings = this.showSettings;
	$scope.appname = this.getAppName();
	$scope.getTemplate = this.getTemplate;
}
DriveController.prototype.getAppName = function() {
	return drive.get_appname();
}
DriveController.prototype.getTemplate = function(name) {
	return 'templates/' + name + '.html';
}
DriveController.prototype.showSettings = function(section) {
	drive.show_settings(section);
}
DriveController.prototype.showConflicts = function(uid) {
	drive.show_conflicts_resolution(uid);
}
DriveController.prototype.quit = function() {
	drive.quit();
}
DriveController.prototype.openRemote = function(uid) {
	drive.open_remote(uid);
}
DriveController.prototype.openLocal = function(uid, path) {
	drive.open_local(uid, path);
}
DriveController.prototype.needAdvMenu = function() {
	return drive.need_adv_menu();
}
DriveController.prototype.isPaused = function() {
	return drive.is_paused();
}
DriveController.prototype.suspendEngines = function() {
	drive.suspend();
}
DriveController.prototype.resumeEngines = function() {
	drive.resume();
}
DriveController.prototype.getAutoUpdate = function() {
	return drive.get_auto_update();
}
DriveController.prototype.getEngines = function() {
	return angular.fromJson(drive.get_engines());
}
DriveController.prototype.appUpdate = function(version) {
	drive.app_update(version);
}
DriveController.prototype.updatePassword = function($scope, uid, password) {
	$scope.currentAction = "CONNECTING";
	$scope.update_password_error = 'CONNECTING';
	when( drive.update_password_async(uid, password)).then(
		function (res) {
			if (res == "") {
				$scope.update_password_error = null;
				$scope.engines = this.getEngines();
				// Waiting for better solution
				top.location.reload();
			} else {
				$scope.update_password_error = res;
				$scope.password = "";
			}
			$scope.currentAction = "";
			$scope.$apply();
		}
	);
}
DriveController.prototype.getUpdateStatus = function() {
	return angular.fromJson(drive.get_update_status());
}