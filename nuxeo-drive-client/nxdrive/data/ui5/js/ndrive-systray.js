var SystrayController = function($scope, $interval, $translate) {
	DriveController.call(this, $scope, $translate);
	var self = this;
	// Set default status
	$scope.engine = null;
	$scope.current_actions = [];
	$scope.last_files = [];
	$scope.syncing_items = 0;
	$scope.autoUpdate = this.getAutoUpdate();
	$scope.app_update = this.getUpdateStatus();
	$scope.confirmAppUpdateDialog = null;
	$scope.confirmAppUpdate = this.confirmAppUdpate;
	$scope.interval = null;

	// Set default action
	$scope.open_local = function(path) {
		self.openLocal($scope.engine.uid, path);
	}
	$scope.open_remote = function() {
		self.openRemote($scope.engine.uid);
	}
	$scope.advanced_systray = this.advancedSystray;
	
	$scope.appUpdate = function() {
		self.appUpdate(this.$scope.confirmAppUpdateDialog);
		this.$scope.confirmAppUpdateDialog = null;
	}
	$scope.updateFiles = function() {
		if ($scope.current_actions.length < 5) {
			$scope.last_files = angular.fromJson(drive.get_last_files($scope.engine.uid, 5-$scope.current_actions.length, "remote")); 
		} else {
			$scope.last_files = [];	
		}
	}
	$scope.update = function() {
		$scope.app_update = angular.fromJson(drive.get_update_status());
		$scope.sync = drive.is_syncing($scope.engine.uid);
		if ($scope.sync == $scope.engine.syncing && $scope.sync != 'syncing') {
			// Nothing to update
			return;
		}
		$scope.engine.syncing = $scope.sync;
		if ($scope.engine.syncing == 'syncing') {
			$scope.syncing_items = drive.get_syncing_items($scope.engine.uid);
			$scope.current_actions = angular.fromJson(drive.get_actions($scope.engine.uid));
		} else {
			$scope.syncing_items = 0;
			$scope.current_actions = [];
		}
		$scope.updateFiles();
	}
	$scope.setEngine = function(engine) {
		$scope.engine = engine;
		$scope.sync = drive.is_syncing($scope.engine.uid);
		$scope.current_actions = angular.fromJson(drive.get_actions(engine.uid));
		$scope.updateFiles();
		if ($scope.interval == null) {
			$scope.interval = $interval($scope.update, 1000);
		}
	}
	if ($scope.engines.length > 0) {
		$scope.bind = true;
		$scope.setEngine($scope.engines[0]);
	} else {
		$scope.bind = false;
		drive.resize(300, 225);
	}
	$scope.getEngineClass = function(engine) {
		if (engine == $scope.engine) {
			return "currentEngine";
		}
		return "";
	}
}
SystrayController.prototype = Object.create(DriveController.prototype);
SystrayController.prototype.constructor = SystrayController;

SystrayController.prototype.advancedSystray = function() {
	drive.advanced_systray();
}
SystrayController.prototype.confirmAppUpdate = function (version) {
	this.$scope.confirmAppUpdateDialog = version;	
}

/**
 * Sample of a CustomSystrayController
 */
function CustomSystrayController($scope, $interval, $translate) {
	SystrayController.call(this, $scope, $interval, $translate);
}
CustomSystrayController.prototype = Object.create(SystrayController.prototype);
CustomSystrayController.prototype.constructor = CustomSystrayController;
CustomSystrayController.prototype.advancedSystray = function() {
	drive.advanced_systray();
}
/*
function($scope, $interval, $translate) {
		$scope.advanced_systray = function() {
			drive.advanced_systray();
		}
		$scope.interval = null;
		$scope.autoUpdate = drive.get_auto_update();
		$scope.setAutoUpdate = drive.set_auto_update;
		$scope.engines = angular.fromJson(drive.get_engines());
		$scope.appUpdate = function() {
			drive.app_update($scope.confirmAppUpdateDialog);
			$scope.confirmAppUpdateDialog = null;
		}
		$scope.app_update = angular.fromJson(drive.get_update_status());
		$scope.confirmAppUpdateDialog = null;
		$scope.confirmAppUpdate = function (version) {
			$scope.confirmAppUpdateDialog = version;	
		}
		$scope.engine = null;
		$scope.current_actions = [];
		$scope.last_files = [];
		$scope.syncing_items = 0;
		$scope.updateFiles = function() {
			if ($scope.current_actions.length < 5) {
				$scope.last_files = angular.fromJson(drive.get_last_files($scope.engine.uid, 5-$scope.current_actions.length, "remote")); 
			} else {
				$scope.last_files = [];	
			}
		}
		$scope.update = function() {
			$scope.app_update = angular.fromJson(drive.get_update_status());
			$scope.sync = drive.is_syncing($scope.engine.uid);
			if ($scope.sync == $scope.engine.syncing && $scope.sync != 'syncing') {
				// Nothing to update
				return;
			}
			$scope.engine.syncing = $scope.sync;
			if ($scope.engine.syncing == 'syncing') {
				$scope.syncing_items = drive.get_syncing_items($scope.engine.uid);
				$scope.current_actions = angular.fromJson(drive.get_actions($scope.engine.uid));
			} else {
				$scope.syncing_items = 0;
				$scope.current_actions = [];
			}
			$scope.updateFiles();
		}
		$scope.setEngine = function(engine) {
			$scope.engine = engine;
			$scope.sync = drive.is_syncing($scope.engine.uid);
			$scope.current_actions = angular.fromJson(drive.get_actions(engine.uid));
			$scope.updateFiles();
			if ($scope.interval == null) {
				$scope.interval = $interval($scope.update, 1000);
			}
		}
		if ($scope.engines.length > 0) {
			$scope.bind = true;
			$scope.setEngine($scope.engines[0]);
		} else {
			$scope.bind = false;
			drive.resize(300, 225);
		}
		$scope.getEngineClass = function(engine) {
			if (engine == $scope.engine) {
				return "currentEngine";
			}
			return "";
		}
		$scope.open_remote = function() {
			drive.open_remote($scope.engine.uid);
		}	
		$scope.open_local = function(path) {
			drive.open_local($scope.engine.uid, path);
		}
		$scope.show_settings = drive.show_settings;
		$scope.quit = drive.quit;
	}

*/