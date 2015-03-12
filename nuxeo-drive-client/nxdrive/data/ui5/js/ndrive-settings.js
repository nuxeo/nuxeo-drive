var SettingsController = function($scope, $interval, $translate) {
	DriveController.call(this, $scope, $translate);
	self = this;
	$scope.accounts = [];
	$scope.section = ""
	$scope.local_folder = "";
	$scope.currentAccount = "";
	$scope.show_activities = drive.show_activities;
	$scope.auto_start = drive.get_auto_start();
	$scope.beta_channel_available = drive.is_beta_channel_available();
	$scope.beta_channel = drive.get_beta_channel();
	$scope.tracking = drive.get_tracking();
	$scope.proxy = angular.fromJson(drive.get_proxy_settings());
	$scope.log_level = drive.get_log_level();
	$scope.setLogLevel = function() {
		drive.set_log_level($scope.log_level);
	}
	$scope.locale = drive.locale();
	$scope.languages = angular.fromJson(drive.get_languages());
	$scope.setLocale = function() {
		console.log("setLocale " + $scope.locale);
		drive.set_language($scope.locale);
		$translate.use($scope.locale);
	}
	$scope.show_file_status = function () {
		drive.show_file_status();
	}
	$scope.reinitNewAccount = function() {
		self.reinitNewAccount($scope);
	}
	$scope.bindServer = function() {
		self.bindServer($scope, $translate);
	}
	$scope.validForm = function() {
		return ($scope.currentAccount.username != '' && $scope.password != ''
			&& $scope.currentAccount.local_folder != '' && $scope.currentAccount.server_url != '');
	}
	$scope.browse = function() {
		$scope.reinitMsgs();
		if ($scope.currentAccount.initialized) {
			return
		}
		$scope.currentAccount.local_folder = drive.browse_folder($scope.currentAccount.local_folder);
	}
	$scope.open_local = function(path) {
		$scope.reinitMsgs();
		drive.open_local('', path);
	}
	$scope.getSectionClass = function(section) {
		if ($scope.section == section) {
			return "active";
		}
		return "";
	}
	$scope.saveProxy = function() {
		$scope.reinitMsgs();
		drive.set_proxy_settings($scope.proxy.config, $scope.proxy.type, $scope.proxy.server, 0, $scope.proxy.authenticated, $scope.proxy.username, $scope.proxy.password)
	}
	$scope.setTracking = function() {
		$scope.reinitMsgs();
		drive.set_tracking($scope.tracking);
	}
	$scope.setAutoStart = function() {
		$scope.reinitMsgs();
		drive.set_auto_start($scope.auto_start)
	}
	$scope.setAutoUpdate = function() {
		$scope.reinitMsgs();
		drive.set_auto_update($scope.auto_update)
	}
	$scope.setBetaChannel = function() {
		$scope.reinitMsgs();
		drive.set_beta_channel($scope.beta_channel)
	}
	$scope.unbindBlur = function() {
		$scope.reinitMsgs();
		button = angular.element(document.querySelector('#unbindButton'));
		button.removeClass("btn-danger");
		button.html($translate.instant("DISCONNECT"));
	}
	$scope.filters = function() {
		$scope.reinitMsgs();
		drive.filters_dialog($scope.currentAccount.uid);
	}
	$scope.setSuccessMessage = function(msg, type) {
		$scope.setMessage(msg, 'success');
	}
	$scope.setErrorMessage = function(msg, type) {
		$scope.setMessage(msg, 'danger');
	}
	$scope.setMessage = function(msg, type) {
		console.log("Message " + type + " : " + msg);
		$scope.message = msg;
		$scope.message_type = type;
	}
	$scope.reinitMsgs = function() {
		$scope.message = "";
		$scope.message_type = "";
	}
	$scope.reinitMsgs();
	$scope.unbindServer = function() {
		button = angular.element(document.querySelector('#unbindButton'));
		if (button.hasClass("btn-danger")) {
			button.html($translate.instant("DISCONNECT"));
			button.removeClass("btn-danger");
			console.log($scope.currentAccount);
			drive.unbind_server($scope.currentAccount.uid)
			$scope.engines = angular.fromJson(drive.get_engines());
			if ($scope.engines.length > 0) {
				$scope.changeAccount($scope.engines[0]);	
			} else {
				$scope.changeAccount($scope.newAccount);
			}
		} else {
			button.addClass("btn-danger");
			button.html($translate.instant("CONFIRM_DISCONNECT"));
		}
	}
	$scope.changeSection = function(section) {
		console.log("Changing section to " + section);
		if (section.length > 9 &&
				section.substr(0,8) == "Accounts") {
			uid = section.substr(9, section.length);
			console.log("Changing section to " + section);
			for (i = 0; i < $scope.engines.length; i++) {
				if ($scope.engines[i].uid == uid) {
					console.log("Find account of " + uid);
					$scope.changeAccount($scope.engines[i]);
				}
			}
			section = "Accounts";
		}
		if (section == $scope.section) {
			return;
		}
		$scope.reinitMsgs();
		$scope.section = section;
	}
	$scope.changeAccount = function(account) {
		$scope.reinitMsgs();
		$scope.currentAccount = account;
	}
	$scope.getAccountClass = function(account) {
		if ($scope.currentAccount == account) {
			return "active";
		}
		return "";
	}
	$scope.reinitNewAccount();
	$scope.changeSection(drive.get_default_section());
	if ($scope.engines.length > 0) {
		if ($scope.currentAccount == "") {
			$scope.changeAccount($scope.engines[0]);
		}
	} else {
		$scope.changeAccount($scope.newAccount);
	}
}

SettingsController.prototype = Object.create(DriveController.prototype);
SettingsController.prototype.constructor = SettingsController;

SettingsController.prototype.reinitNewAccount = function ($scope) {
	$scope.newAccount = {initialized: false};
	$scope.newAccount.local_folder = drive.get_default_nuxeo_drive_folder();
}
SettingsController.prototype.bindServer = function($scope, $translate) {
	$scope.reinitMsgs();
	local_folder = $scope.currentAccount.local_folder;
	res = drive.bind_server($scope.currentAccount.local_folder, $scope.currentAccount.server_url, $scope.currentAccount.username, $scope.password, $scope.currentAccount.name);
	if (res == "") {
		$scope.password = "";
		$scope.engines = angular.fromJson(drive.get_engines());
		$scope.reinitNewAccount();
		for (i = 0; i < $scope.engines.length; i++) {
			if ($scope.engines[i].local_folder == local_folder) {
				$scope.changeAccount($scope.engines[i]);
				break;
			}
		}
		$scope.setSuccessMessage($translate.instant("CONNECTION_SUCCESS"));
	} else {
		$scope.setErrorMessage($translate.instant(res));
	}
}