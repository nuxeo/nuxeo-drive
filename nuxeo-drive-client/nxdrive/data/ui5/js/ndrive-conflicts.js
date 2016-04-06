var ConflictsController = function($scope, $interval, $translate) {
	DriveController.call(this, $scope, $translate);
	var self = this;
	// Set default action
	$scope.open_local = function(path) {
		self.openLocal(path);
	}
	$scope.open_remote = function(remote_ref, remote_name) {
		console.log(remote_name + ' (' + remote_ref + ')')
		self.openRemote(remote_ref, remote_name);
	}
	$scope.show_metadata = function(path) {
		self.showMetadata($scope.engine.uid, path);
	}
	$scope.resolve_with_duplicate = function(uid) {
		self.resolveDuplicate(uid);
		self.updateConflicts($scope);
	}
	$scope.resolve_with_local = function(uid) {
		self.resolveLocal(uid);
		self.updateConflicts($scope);
	}
	$scope.resolve_with_remote = function(uid) {
		self.resolveRemote(uid);
		self.updateConflicts($scope);
	}
	$scope.unsynchronize_pair = function(uid) {
		self.unsynchronizePair(uid);
		self.updateErrors($scope);
	}
	$scope.retry_pair = function(uid) {
		self.retryPair(uid);
		self.updateErrors($scope);
	}
	self.updateErrors($scope);
	self.updateConflicts($scope);
}
ConflictsController.prototype = Object.create(DriveController.prototype);
ConflictsController.prototype.constructor = ConflictsController;

ConflictsController.prototype.updateErrors = function($scope) {
	$scope.errors = angular.fromJson(drive.get_errors());
	var ignoreds = angular.fromJson(drive.get_ignoreds());
	for (ignore in ignoreds) {
		if (ignoreds[ignore].last_error !== "READONLY" &&
				ignoreds[ignore].last_error !== "PARENT_UNSYNC" &&
				ignoreds[ignore].last_error !== "LOCKED" &&
				ignoreds[ignore].last_error !== "MANUAL") {
			ignoreds[ignore].ignore_reason = "IGNORE_REASON_UNKNOWN";
		} else {
			ignoreds[ignore].ignore_reason = "IGNORE_REASON_" + ignoreds[ignore].last_error;
		}
	}
	$scope.ignoreds = ignoreds;
}
ConflictsController.prototype.updateConflicts = function($scope, $interval) {
	self = this;
	$scope.conflicts = angular.fromJson(drive.get_conflicts());
	for (var i=0; i<$scope.conflicts.length; i++) {
		if ($scope.conflicts[i].last_error == "DUPLICATING") {
			setTimeout( function() {
				self.updateConflicts($scope, $interval);
				$scope.$apply();
			}, 1000);
		}
	}
}
ConflictsController.prototype.openRemote = function(remote_ref, remote_name) {
	drive.open_remote(remote_ref, remote_name);
}
ConflictsController.prototype.openLocal = function(path) {
	drive.open_local(path);
}
ConflictsController.prototype.retryPair = function(uid) {
	drive.retry_pair(uid);
}
ConflictsController.prototype.unsynchronizePair = function(uid) {
	drive.unsynchronize_pair(uid);
}
ConflictsController.prototype.resolveLocal = function(uid) {
	drive.resolve_with_local(uid);
}
ConflictsController.prototype.resolveRemote = function(uid) {
	drive.resolve_with_remote(uid);
}
ConflictsController.prototype.resolveDuplicate = function(uid) {
	drive.resolve_with_duplicate(uid);
}