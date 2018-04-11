var NetworkErrorController = function($scope, $translate) {
    DriveController.call(this, $scope, $translate);
    self = this;
    $scope.error = angular.fromJson(drive.get_last_error());
    // See http://doc.qt.io/qt-4.8/qnetworkreply.html#NetworkError-enum
    $scope.error.label = "NETWORK_ERROR_";
    if ($scope.error.code < 100) {
        $scope.error.simple_label = "NETWORK_ERROR_ClientNetwork";
    } else if ($scope.error.code < 200) {
        $scope.error.simple_label = "NETWORK_ERROR_Proxy";
    } else if ($scope.error.code < 300) {
        $scope.error.simple_label = "NETWORK_ERROR_ServerError";
    } else if ($scope.error.code < 400) {
        $scope.error.simple_label = "NETWORK_ERROR_ProtocolError";
    }
    switch ($scope.error.code) {
        case 1:
            $scope.error.label += "ConnectionRefusedError";
            break;
        case 2:
            $scope.error.label += "RemoteHostClosedError";
            break;
        case 3:
            $scope.error.label += "HostNotFoundError";
            break;
        case 4:
            $scope.error.label += "TimeoutError";
            break;
        case 5:
            $scope.error.label += "OperationCanceledError";
            break;
        case 6:
            $scope.error.label += "SslHandshakeFailedError";
            break;
        case 7:
            $scope.error.label += "TemporaryNetworkFailureError";
            break;
        case 101:
            $scope.error.label += "ProxyConnectionRefusedError";
            break;
        case 102:
            $scope.error.label += "ProxyConnectionClosedError";
            break;
        case 103:
            $scope.error.label += "ProxyNotFoundError";
            break;
        case 104:
            $scope.error.label += "ProxyTimeoutError";
            break;
        case 105:
            $scope.error.label += "ProxyAuthenticationRequiredError";
            break;
        case 201:
            $scope.error.label += "ContentAccessDenied";
            break;
        case 202:
            $scope.error.label += "ContentOperationNotPermittedError";
            break;
        case 203:
            $scope.error.label += "ContentNotFoundError";
            break;
        case 204:
            $scope.error.label += "AuthenticationRequiredError";
            break;
        case 205:
            $scope.error.label += "ContentReSendError";
            break;
        case 301:
            $scope.error.label += "ProtocolUnknownError";
            break;
        case 302:
            $scope.error.label += "ProtocolInvalidOperationError";
            break;
        case 99:
            $scope.error.label += "UnknownNetworkError";
            break;
        case 199:
            $scope.error.label += "UnknownProxyError";
            break;
        case 299:
            $scope.error.label += "UnknownContentError";
            break;
        case 399:
            $scope.error.label += "ProtocolFailure";
            break;
        default:
            $scope.error.label += "Unknown";
            break;
    }
}

NetworkErrorController.prototype = Object.create(DriveController.prototype);
NetworkErrorController.prototype.constructor = NetworkErrorController;
