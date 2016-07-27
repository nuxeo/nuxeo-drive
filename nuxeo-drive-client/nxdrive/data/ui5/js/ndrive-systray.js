var SystrayController = function($scope, $timeout, $translate) {
	DriveController.call(this, $scope, $translate);
	var self = this;
	// Set default status
	$scope.engine = null;
	$scope.current_actions = [];
	$scope.last_files = [];
	$scope.notifications = [];
	$scope.syncing_items = 0;
	$scope.autoUpdate = this.getAutoUpdate();
	$scope.app_update = this.getUpdateStatus();
	$scope.update_channel = ''
	$scope.confirmAppUpdateDialog = null;
	$scope.confirmAppUpdate = function(version) {
		$scope.updateChannel = $scope.betaChannel ? 'beta ' : '';
		$scope.confirmAppUpdateDialog = version;	
	}
	$scope.interval = null;

	// Set default action
	$scope.open_local = function(path) {
		self.openLocal($scope.engine.uid, path);
	}
	$scope.open_remote = function() {
		self.openRemote($scope.engine.uid);
	}
	$scope.show_metadata = function(path) {
		self.showMetadata($scope.engine.uid, path);
	}
	$scope.advanced_systray = this.advancedSystray;
	
	$scope.appUpdate = function() {
		self.appUpdate($scope.confirmAppUpdateDialog);
		$scope.app_update = ['updating', $scope.confirmAppUpdateDialog, 0];
		$scope.confirmAppUpdateDialog = null;
	}
	$scope.updateFiles = function() {
		self.getLastFiles($scope);
	}
	$scope.update = function() {
		$scope.interval = null;
		$scope.app_update = angular.fromJson(drive.get_update_status());
		$scope.sync = drive.is_syncing($scope.engine.uid);
		if ($scope.sync == $scope.engine.syncing && $scope.sync != 'syncing') {
			// Nothing to update
			if ($scope.interval === null ) {
				$scope.interval = $timeout($scope.update, 1000);
			}
			return;
		}
		$scope.engine.syncing = $scope.sync;
		if ($scope.engine.syncing == 'syncing') {
			$scope.engine.syncing_count = drive.get_syncing_items($scope.engine.uid);
			$scope.current_actions = angular.fromJson(drive.get_actions($scope.engine.uid));
		} else {
			$scope.engine.syncing_count = 0;
			$scope.current_actions = [];
		}
		$scope.updateFiles();
		if ($scope.interval === null ) {
			$scope.interval = $timeout($scope.update, 1000);
		}
	}
	$scope.triggerNotification = function(notification) {
		drive.trigger_notification(notification.uid);
	}
	$scope.discardNotification = function(notification) {
		drive.discard_notification(notification.uid);
		$scope.notifications.splice($scope.notifications.indexOf(notification),1);
	}
	$scope.setEngine = function(engine) {
		$scope.engine = engine;
		$scope.engine.syncing_count = drive.get_syncing_items($scope.engine.uid);
		$scope.sync = drive.is_syncing($scope.engine.uid);
		notifications = [];
		notifs = angular.fromJson(drive.get_notifications($scope.engine.uid));
		for ( var i in notifs ) {
			if (notifs[i].systray && !notifs[i].discard) {
				notifications.push(notifs[i]);
			}
		}
		$scope.notifications = notifications;
		$scope.current_actions = angular.fromJson(drive.get_actions(engine.uid));
		$scope.updateFiles();
		if ($scope.interval === null ) {
			$scope.interval = $timeout($scope.update, 1000);
		}
	}
	self.init($scope);
	$scope.getEngineClass = function(engine) {
		if (engine == $scope.engine) {
			return "currentEngine";
		}
		return "";
	}
}
SystrayController.prototype = Object.create(DriveController.prototype);
SystrayController.prototype.constructor = SystrayController;
SystrayController.prototype.init = function($scope) {
	if ($scope.engines.length > 0) {
		$scope.bind = true;
		$scope.setEngine($scope.engines[0]);
	} else {
		$scope.bind = false;
		drive.resize(300, 280);
	}
}
SystrayController.prototype.showMetadata = function(uid, path) {
	drive.show_metadata(uid, path);
}
SystrayController.prototype.advancedSystray = function() {
	drive.advanced_systray();
}
SystrayController.prototype.getLastFiles = function($scope) {
	if ($scope.current_actions.length < 5) {
		$scope.last_files = angular.fromJson(drive.get_last_files($scope.engine.uid, 5-$scope.current_actions.length, null)); 
	} else {
		$scope.last_files = [];	
	}
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
