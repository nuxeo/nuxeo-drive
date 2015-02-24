// Add endsWith to String prototype
String.prototype.endsWith = function(suffix) {
    return this.indexOf(suffix, this.length - suffix.length) !== -1;
};
var DRIVE_LOADS = 0;
function drive_init(callback, add_includes) {
	// Includes
	var includes = ['js/angular.min.js','js/angular-translate.min.js','js/jquery-2.1.3.min.js','js/bootstrap.min.js','i18n.js', 'css/bootstrap.min.css', 'css/ndrive.css'];
	includes = includes.concat(add_includes);
	
	for (var i = 0; i < includes.length; i++) {
		if (includes[i].endsWith("css")) {
			script = document.createElement('link');
			script.setAttribute('href', includes[i]);
			script.setAttribute('rel', "stylesheet");
		} else if (includes[i].endsWith("js")) {
			script = document.createElement('script');
			script.setAttribute('src', includes[i]);
			DRIVE_LOADS++;
		}
		script.onload = function() {
			DRIVE_LOADS--;
			var test = i;
			if (DRIVE_LOADS == 0) {
				callback();
			}
		}
		document.head.appendChild(script)
	}
}
function drive_module(name) {
	if (DRIVE_LOADS > 0) {
		console.log("Should wait");
		return null;
	}
	app = angular.module(name, ['pascalprecht.translate']);
	app.config(function ($translateProvider) {
		languages = angular.fromJson(drive.get_languages());
		for (i=0; i<languages.length; i++) {
			$translateProvider.translations(languages[i][0], eval("LABELS." + languages[i][0]));
		}
		$translateProvider.preferredLanguage(drive.locale());
	});
	app.run(function() {
		$("body").css('visibility', 'visible');
	});
	return app;
}
tracker = drive.get_tracker_id();
if (tracker != "") {
	(function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
	(i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
	m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
	})(window,document,'script','http://www.google-analytics.com/analytics.js','ga');

	ga('create', tracker, 'auto');
	ga('send', 'pageview');
}

// Default controller
DriveController = function($scope, $translate) {
	// Map default drive API
	$scope.engines = this.getEngines();
	$scope.open_remote = this.openRemote;
	$scope.open_local = this.openLocal;
	$scope.app_update = this.appUpdate;
	$scope.get_update_status = this.getUpdateStatus;
	$scope.setAutoUpdate = this.setAutoUpdate;
	$scope.quit = this.quit;
	$scope.show_settings = this.showSettings;
}
DriveController.prototype.showSettings = function() {
	drive.show_settings();
}
DriveController.prototype.quit = function() {
	drive.quit();
}
DriveController.prototype.setAutoUpdate = function(value) {
	drive.set_auto_update(value);
}
DriveController.prototype.openRemote = function(uid) {
	drive.open_remote(uid);
}
DriveController.prototype.openLocal = function(uid, path) {
	drive.open_local(uid, path);
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
DriveController.prototype.getUpdateStatus = function() {
	return angular.fromJson(drive.get_update_status());
}