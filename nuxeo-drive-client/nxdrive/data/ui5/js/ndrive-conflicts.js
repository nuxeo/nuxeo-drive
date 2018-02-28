var ConflictsController = function($scope, $interval, $translate) {
	DriveController.call(this, $scope, $translate);
	var self = this;
	// Set default action
	$scope.open_local = function(path) {
		self.openLocal(path);
	}
	$scope.open_remote = function(remote_ref, remote_name) {
		self.openRemote(remote_ref, remote_name);
	}
	$scope.show_metadata = function(path) {
		self.showMetadata($scope.engine.uid, path);
	}
	$scope.resolve_with_local = function(uid) {
		self.resolveLocal(uid);
		self.updateConflicts($scope);
	}
	$scope.resolve_with_remote = function(uid) {
		self.resolveRemote(uid);
		self.updateConflicts($scope);
	}
	$scope.unsynchronize_pair = function(uid, reason) {
		self.unsynchronizePair(uid, reason);
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
	var errors = angular.fromJson(drive.get_errors()),
	    ignoreds = angular.fromJson(drive.get_ignoreds()),
	    reasons = [
	        'READONLY',
	        'PARENT_UNSYNC',
	        'LOCKED',
	        'MANUAL',
	        'DEDUP',
	        'CORRUPT',
	    ];

	for (error in errors) {
		if (reasons.indexOf(errors[error].last_error) < 0) {
			errors[error].error_reason = "ERROR_REASON_UNKNOWN";
		} else {
			errors[error].error_reason = "ERROR_REASON_" + errors[error].last_error;
		}
	}
	$scope.errors = errors;

	for (var ignore in ignoreds) {
		if (reasons.indexOf(ignoreds[ignore].last_error) < 0) {
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

	when(drive.get_conflicts_with_fullname_async()).then( function(res) {
		var conflicts = angular.fromJson(res);
		// Dont change the all array in case some action has already been taken
		for (var i=0; i<$scope.conflicts.length; i++) {
			if (i >= conflicts.length) break;
			if (conflicts[i].id == $scope.conflicts[i].id) {
				$scope.conflicts[i].last_contributor = conflicts[i].last_contributor;
			}
		}
		$scope.$apply();
	});

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
ConflictsController.prototype.unsynchronizePair = function(uid, reason) {
	drive.unsynchronize_pair(uid, reason);
}
ConflictsController.prototype.resolveLocal = function(uid) {
	drive.resolve_with_local(uid);
}
ConflictsController.prototype.resolveRemote = function(uid) {
	drive.resolve_with_remote(uid);
}
