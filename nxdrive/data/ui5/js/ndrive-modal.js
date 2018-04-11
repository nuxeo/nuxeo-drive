var ModalController = function($scope, $interval, $translate) {
    DriveController.call(this, $scope, $translate);
    self = this;
    $scope.message = drive.get_message();
    $scope.buttons = angular.fromJson(drive.get_buttons());
    $scope.result = function(uid) {
        drive.result(uid);
    }
}

ModalController.prototype = Object.create(DriveController.prototype);
ModalController.prototype.constructor = ModalController;
