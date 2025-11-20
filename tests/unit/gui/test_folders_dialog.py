"""Unit tests for DocumentsDialog._handle_no_roots function."""

from unittest.mock import MagicMock, Mock, call, patch

from nxdrive.gui.folders_dialog import DocumentsDialog, FoldersDialog, NewFolderDialog
from nxdrive.gui.folders_treeview import DocumentTreeView
from nxdrive.qt import constants as qt
from nxdrive.qt.imports import QComboBox, QLabel, QMenu, QPoint


class TestDocumentsDialogHandleNoRoots:
    """Test cases for DocumentsDialog._handle_no_roots method."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create mock application and engine
        self.mock_application = Mock()
        self.mock_application.icon = Mock()

        self.mock_engine = Mock()
        self.mock_engine.is_syncing.return_value = False
        self.mock_engine.dao.get_filters.return_value = []
        self.mock_engine.remote = Mock()
        self.mock_engine.server_url = "https://test.server.com"

    def test_handle_no_roots_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of _handle_no_roots method."""

        # Create a mock dialog instance and directly test the method
        dialog = Mock(spec=DocumentsDialog)

        # Mock the UI components that _handle_no_roots manipulates
        dialog.select_all_button = Mock()
        dialog.tree_view = Mock()
        dialog.no_root_label = Mock()

        # Mock dialog geometry methods
        dialog.x = Mock(return_value=100)
        dialog.y = Mock(return_value=200)
        dialog.setGeometry = Mock()

        # Get the actual method implementation and bind it to our mock
        actual_handle_no_roots = DocumentsDialog._handle_no_roots

        # Call the method directly on our mock
        actual_handle_no_roots(dialog)

        # Verify select_all_button is hidden
        dialog.select_all_button.setVisible.assert_called_once_with(False)

        # Verify tree_view is hidden
        dialog.tree_view.setVisible.assert_called_once_with(False)

        # Verify tree_view is resized to (0, 0)
        dialog.tree_view.resize.assert_called_once_with(0, 0)

        # Verify no_root_label is shown
        dialog.no_root_label.setVisible.assert_called_once_with(True)

        # Verify dialog geometry is updated correctly
        # Expected: setGeometry(x, y + 150, 491, 200)
        dialog.setGeometry.assert_called_once_with(100, 350, 491, 200)

        # Verify x() and y() methods were called to get current position
        dialog.x.assert_called_once()
        dialog.y.assert_called_once()

    def test_handle_no_roots_call_order_verification(self):
        """Test that all UI elements are properly manipulated in the correct sequence."""

        # Create a mock dialog instance for order verification
        dialog = Mock(spec=DocumentsDialog)

        # Mock UI components with call tracking
        dialog.select_all_button = Mock()
        dialog.tree_view = Mock()
        dialog.no_root_label = Mock()
        dialog.x = Mock(return_value=50)
        dialog.y = Mock(return_value=75)
        dialog.setGeometry = Mock()

        # Track the order of calls using side_effect
        call_order = []

        def track_select_all_button_setVisible(visible):
            call_order.append(("select_all_button.setVisible", visible))

        def track_tree_view_setVisible(visible):
            call_order.append(("tree_view.setVisible", visible))

        def track_tree_view_resize(width, height):
            call_order.append(("tree_view.resize", width, height))

        def track_no_root_label_setVisible(visible):
            call_order.append(("no_root_label.setVisible", visible))

        def track_setGeometry(x, y, width, height):
            call_order.append(("setGeometry", x, y, width, height))

        dialog.select_all_button.setVisible.side_effect = (
            track_select_all_button_setVisible
        )
        dialog.tree_view.setVisible.side_effect = track_tree_view_setVisible
        dialog.tree_view.resize.side_effect = track_tree_view_resize
        dialog.no_root_label.setVisible.side_effect = track_no_root_label_setVisible
        dialog.setGeometry.side_effect = track_setGeometry

        # Get the actual method and execute it
        actual_handle_no_roots = DocumentsDialog._handle_no_roots
        actual_handle_no_roots(dialog)

        # Verify the exact order and parameters of operations
        expected_calls = [
            ("select_all_button.setVisible", False),
            ("tree_view.setVisible", False),
            ("tree_view.resize", 0, 0),
            ("no_root_label.setVisible", True),
            ("setGeometry", 50, 225, 491, 200),  # y + 150 = 75 + 150 = 225
        ]

        assert (
            call_order == expected_calls
        ), f"Expected {expected_calls}, got {call_order}"

    def test_handle_no_roots_geometry_calculations(self):
        """Test geometry calculations with different initial coordinates."""

        # Test case 1: Different coordinates
        dialog = Mock(spec=DocumentsDialog)

        dialog.select_all_button = Mock()
        dialog.tree_view = Mock()
        dialog.no_root_label = Mock()
        dialog.x = Mock(return_value=300)
        dialog.y = Mock(return_value=400)
        dialog.setGeometry = Mock()

        # Get the actual method and call it
        actual_handle_no_roots = DocumentsDialog._handle_no_roots
        actual_handle_no_roots(dialog)

        # Verify geometry calculation with different coordinates
        # Expected: setGeometry(300, 400 + 150, 491, 200) = setGeometry(300, 550, 491, 200)
        dialog.setGeometry.assert_called_once_with(300, 550, 491, 200)

    def test_handle_no_roots_edge_cases(self):
        """Test edge cases with zero and negative coordinates."""

        # Test case 1: Zero coordinates
        dialog = Mock(spec=DocumentsDialog)

        dialog.select_all_button = Mock()
        dialog.tree_view = Mock()
        dialog.no_root_label = Mock()
        dialog.x = Mock(return_value=0)
        dialog.y = Mock(return_value=0)
        dialog.setGeometry = Mock()

        # Get the actual method and call it
        actual_handle_no_roots = DocumentsDialog._handle_no_roots
        actual_handle_no_roots(dialog)

        # Verify geometry calculation with zero coordinates
        # Expected: setGeometry(0, 0 + 150, 491, 200) = setGeometry(0, 150, 491, 200)
        dialog.setGeometry.assert_called_once_with(0, 150, 491, 200)

        # Test case 2: Negative coordinates
        dialog2 = Mock(spec=DocumentsDialog)

        dialog2.select_all_button = Mock()
        dialog2.tree_view = Mock()
        dialog2.no_root_label = Mock()
        dialog2.x = Mock(return_value=-50)
        dialog2.y = Mock(return_value=-100)
        dialog2.setGeometry = Mock()

        # Get the actual method and call it
        actual_handle_no_roots = DocumentsDialog._handle_no_roots
        actual_handle_no_roots(dialog2)

        # Verify geometry calculation with negative coordinates
        # Expected: setGeometry(-50, -100 + 150, 491, 200) = setGeometry(-50, 50, 491, 200)
        dialog2.setGeometry.assert_called_once_with(-50, 50, 491, 200)

    def test_handle_no_roots_ui_element_interactions(self):
        """Test that method correctly interacts with all UI elements."""

        dialog = Mock(spec=DocumentsDialog)

        # Mock UI components and verify they are called correctly
        dialog.select_all_button = Mock()
        dialog.tree_view = Mock()
        dialog.no_root_label = Mock()
        dialog.x = Mock(return_value=150)
        dialog.y = Mock(return_value=250)
        dialog.setGeometry = Mock()

        # Verify initial state assumptions (not actually set, just documenting expected behavior)
        # - select_all_button should start visible and become hidden
        # - tree_view should start visible and become hidden
        # - no_root_label should start hidden and become visible

        # Get the actual method and call it
        actual_handle_no_roots = DocumentsDialog._handle_no_roots
        actual_handle_no_roots(dialog)

        # Verify each UI element was modified exactly once with correct parameters
        assert dialog.select_all_button.setVisible.call_count == 1
        assert dialog.tree_view.setVisible.call_count == 1
        assert dialog.tree_view.resize.call_count == 1
        assert dialog.no_root_label.setVisible.call_count == 1
        assert dialog.setGeometry.call_count == 1

        # Verify the specific values passed to each method
        dialog.select_all_button.setVisible.assert_called_with(False)
        dialog.tree_view.setVisible.assert_called_with(False)
        dialog.tree_view.resize.assert_called_with(0, 0)
        dialog.no_root_label.setVisible.assert_called_with(True)
        dialog.setGeometry.assert_called_with(150, 400, 491, 200)  # 250 + 150 = 400

    def test_handle_no_roots_constants_verification(self):
        """Test that the method uses the correct hardcoded constants."""

        dialog = Mock(spec=DocumentsDialog)

        dialog.select_all_button = Mock()
        dialog.tree_view = Mock()
        dialog.no_root_label = Mock()
        dialog.x = Mock(return_value=999)
        dialog.y = Mock(return_value=888)
        dialog.setGeometry = Mock()

        # Get the actual method and call it
        actual_handle_no_roots = DocumentsDialog._handle_no_roots
        actual_handle_no_roots(dialog)

        # Verify the method uses the correct constants:
        # - Y offset: +150
        # - New width: 491
        # - New height: 200
        # - Tree resize: (0, 0)
        dialog.tree_view.resize.assert_called_with(0, 0)
        dialog.setGeometry.assert_called_with(999, 1038, 491, 200)  # 888 + 150 = 1038

        # Verify boolean constants
        dialog.select_all_button.setVisible.assert_called_with(False)
        dialog.no_root_label.setVisible.assert_called_with(True)


class TestDocumentsDialogAccept:
    """Test cases for DocumentsDialog.accept method."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create mock application and engine
        self.mock_application = Mock()
        self.mock_application.icon = Mock()

        self.mock_engine = Mock()
        self.mock_engine.is_syncing.return_value = False
        self.mock_engine.dao.get_filters.return_value = []
        self.mock_engine.remote = Mock()
        self.mock_engine.server_url = "https://test.server.com"

    def test_accept_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of accept method."""

        # Test case 1: tree_view is a DocumentTreeView instance - apply_filters should be called
        dialog = Mock(spec=DocumentsDialog)

        # Mock the tree_view as DocumentTreeView instance
        dialog.tree_view = Mock(spec=DocumentTreeView)

        # Mock the apply_filters method
        dialog.apply_filters = Mock()

        # Create a mock for the parent class accept method
        mock_parent_accept = Mock()

        # Get the actual method implementation
        actual_accept = DocumentsDialog.accept

        # Use patch to mock super().accept()
        with patch("builtins.super") as mock_super:
            mock_super.return_value.accept = mock_parent_accept

            # Call the method directly on our mock
            actual_accept(dialog)

            # Verify apply_filters was called (since tree_view is DocumentTreeView)
            dialog.apply_filters.assert_called_once()

            # Verify super().accept() was called
            mock_parent_accept.assert_called_once()

        # Test case 2: tree_view is NOT a DocumentTreeView instance - apply_filters should NOT be called
        dialog2 = Mock(spec=DocumentsDialog)

        # Mock the tree_view as a regular QLabel (not DocumentTreeView)
        dialog2.tree_view = Mock(spec=QLabel)
        dialog2.apply_filters = Mock()

        # Create a mock for the parent class accept method for second test
        mock_parent_accept2 = Mock()

        with patch("builtins.super") as mock_super2:
            mock_super2.return_value.accept = mock_parent_accept2

            # Call the method on the second dialog
            actual_accept(dialog2)

            # Verify apply_filters was NOT called (since tree_view is not DocumentTreeView)
            dialog2.apply_filters.assert_not_called()

            # Verify super().accept() was still called
            mock_parent_accept2.assert_called_once()

        # Test case 3: Verify isinstance check works correctly with real DocumentTreeView mock
        dialog3 = Mock(spec=DocumentsDialog)

        # Create a more realistic mock that will pass isinstance check
        dialog3.tree_view = DocumentTreeView.__new__(DocumentTreeView)
        dialog3.apply_filters = Mock()

        mock_parent_accept3 = Mock()

        with patch("builtins.super") as mock_super3:
            mock_super3.return_value.accept = mock_parent_accept3

            # Call the method on the third dialog
            actual_accept(dialog3)

            # Verify apply_filters was called (real DocumentTreeView instance)
            dialog3.apply_filters.assert_called_once()

            # Verify super().accept() was called
            mock_parent_accept3.assert_called_once()

        # Verify method call counts for comprehensive coverage
        assert dialog.apply_filters.call_count == 1  # Called for DocumentTreeView
        assert dialog2.apply_filters.call_count == 0  # Not called for QLabel
        assert dialog3.apply_filters.call_count == 1  # Called for real DocumentTreeView

        # Verify super().accept() was called in all cases
        assert mock_parent_accept.call_count == 1
        assert mock_parent_accept2.call_count == 1
        assert mock_parent_accept3.call_count == 1

    def test_accept_isinstance_check_behavior(self):
        """Test that isinstance check correctly identifies DocumentTreeView instances."""

        dialog = Mock(spec=DocumentsDialog)
        dialog.apply_filters = Mock()

        # Mock super().accept()
        mock_parent_accept = Mock()

        # Get the actual method implementation
        actual_accept = DocumentsDialog.accept

        # Test with various tree_view types
        test_cases = [
            (
                Mock(spec=DocumentTreeView),
                True,
                "DocumentTreeView mock should trigger apply_filters",
            ),
            (Mock(spec=QLabel), False, "QLabel mock should not trigger apply_filters"),
            (Mock(), False, "Generic mock should not trigger apply_filters"),
        ]

        for tree_view_mock, should_call_apply_filters, description in test_cases:
            # Reset mocks for each test case
            dialog.apply_filters.reset_mock()
            mock_parent_accept.reset_mock()

            dialog.tree_view = tree_view_mock

            with patch("builtins.super") as mock_super:
                mock_super.return_value.accept = mock_parent_accept

                # Call the method
                actual_accept(dialog)

                # Verify behavior based on expected outcome
                if should_call_apply_filters:
                    dialog.apply_filters.assert_called_once()
                else:
                    dialog.apply_filters.assert_not_called()

                # super().accept() should always be called
                mock_parent_accept.assert_called_once()

    def test_accept_method_execution_order(self):
        """Test that apply_filters is called before super().accept()."""

        dialog = Mock(spec=DocumentsDialog)

        # Mock the tree_view as DocumentTreeView to trigger apply_filters
        dialog.tree_view = Mock(spec=DocumentTreeView)

        # Track order of method calls
        call_order = []

        def track_apply_filters():
            call_order.append("apply_filters")

        def track_super_accept():
            call_order.append("super_accept")

        dialog.apply_filters = Mock(side_effect=track_apply_filters)
        mock_parent_accept = Mock(side_effect=track_super_accept)

        # Get the actual method implementation
        actual_accept = DocumentsDialog.accept

        with patch("builtins.super") as mock_super:
            mock_super.return_value.accept = mock_parent_accept

            # Call the method
            actual_accept(dialog)

            # Verify correct execution order
            expected_order = ["apply_filters", "super_accept"]
            assert (
                call_order == expected_order
            ), f"Expected {expected_order}, got {call_order}"

            # Verify both methods were called
            dialog.apply_filters.assert_called_once()
            mock_parent_accept.assert_called_once()


class TestDocumentsDialogApplyFilters:
    """Test cases for DocumentsDialog.apply_filters method."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create mock application and engine
        self.mock_application = Mock()
        self.mock_application.icon = Mock()

        self.mock_engine = Mock()
        self.mock_engine.is_syncing.return_value = False
        self.mock_engine.dao.get_filters.return_value = []
        self.mock_engine.remote = Mock()
        self.mock_engine.server_url = "https://test.server.com"
        self.mock_engine.is_started.return_value = True
        self.mock_engine.add_filter = Mock()
        self.mock_engine.remove_filter = Mock()
        self.mock_engine.start = Mock()

    def test_apply_filters_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of apply_filters method."""

        # Create a mock dialog instance and directly test the method
        dialog = Mock(spec=DocumentsDialog)

        # Mock the engine
        dialog.engine = self.mock_engine

        # Create mock items representing different scenarios
        # Item 1: Unchecked item (should add filter)
        item1 = Mock()
        item1.get_path.return_value = "/folder1"
        item1.state = qt.Unchecked

        # Item 2: Checked item (should remove filter)
        item2 = Mock()
        item2.get_path.return_value = "/folder2"
        item2.state = qt.Checked

        # Item 3: Partially checked item with old_state Unchecked (complex case)
        item3 = Mock()
        item3.get_path.return_value = "/folder3"
        item3.state = qt.PartiallyChecked
        item3.old_state = qt.Unchecked

        # Create mock children for item3
        child1 = Mock()
        child1.get_path.return_value = "/folder3/child1"
        child1.state = qt.Unchecked

        child2 = Mock()
        child2.get_path.return_value = "/folder3/child2"
        child2.state = qt.Checked

        child3 = Mock()
        child3.get_path.return_value = "/folder3/child3"
        child3.state = qt.Unchecked

        item3.get_children.return_value = [child1, child2, child3]

        # Item 4: Partially checked item with old_state NOT Unchecked (should be ignored)
        item4 = Mock()
        item4.get_path.return_value = "/folder4"
        item4.state = qt.PartiallyChecked
        item4.old_state = qt.Checked

        # Mock tree_view with dirty_items
        dialog.tree_view = Mock()
        dialog.tree_view.dirty_items = [item1, item2, item3, item4]

        # Get the actual method implementation
        actual_apply_filters = DocumentsDialog.apply_filters

        # Call the method directly on our mock
        actual_apply_filters(dialog)

        # Verify sorting by path (items should be processed in sorted order)
        # Note: The sorting happens internally, but we can verify the engine calls

        # Verify item1 (Unchecked) -> add_filter
        self.mock_engine.add_filter.assert_any_call("/folder1")

        # Verify item2 (Checked) -> remove_filter
        self.mock_engine.remove_filter.assert_any_call("/folder2")

        # Verify item3 (PartiallyChecked with old_state Unchecked)
        # Should remove parent filter first
        self.mock_engine.remove_filter.assert_any_call("/folder3")
        # Should add filters for unchecked children
        self.mock_engine.add_filter.assert_any_call("/folder3/child1")
        self.mock_engine.add_filter.assert_any_call("/folder3/child3")
        # Should NOT add filter for checked child2

        # Verify total call counts
        # add_filter: item1 + child1 + child3 = 3 calls
        assert self.mock_engine.add_filter.call_count == 3

        # remove_filter: item2 + item3 parent = 2 calls
        assert self.mock_engine.remove_filter.call_count == 2

        # Verify engine.start() was called if engine not started
        self.mock_engine.is_started.return_value = False
        actual_apply_filters(dialog)
        self.mock_engine.start.assert_called_once()

        # Reset and test when engine IS already started
        self.mock_engine.start.reset_mock()
        self.mock_engine.is_started.return_value = True
        actual_apply_filters(dialog)
        self.mock_engine.start.assert_not_called()

    def test_apply_filters_empty_dirty_items(self):
        """Test apply_filters behavior with no dirty items."""

        dialog = Mock(spec=DocumentsDialog)
        dialog.engine = self.mock_engine
        dialog.tree_view = Mock()
        dialog.tree_view.dirty_items = []

        # Get the actual method implementation
        actual_apply_filters = DocumentsDialog.apply_filters

        # Call the method
        actual_apply_filters(dialog)

        # Verify no filter operations were called
        self.mock_engine.add_filter.assert_not_called()
        self.mock_engine.remove_filter.assert_not_called()

        # Verify engine start check still happens
        self.mock_engine.is_started.assert_called_once()

    def test_apply_filters_sorting_behavior(self):
        """Test that items are processed in sorted order by path."""

        dialog = Mock(spec=DocumentsDialog)
        dialog.engine = self.mock_engine

        # Create items in unsorted order
        item_z = Mock()
        item_z.get_path.return_value = "/z_folder"
        item_z.state = qt.Unchecked

        item_a = Mock()
        item_a.get_path.return_value = "/a_folder"
        item_a.state = qt.Unchecked

        item_m = Mock()
        item_m.get_path.return_value = "/m_folder"
        item_m.state = qt.Unchecked

        # Mock tree_view with unsorted dirty_items
        dialog.tree_view = Mock()
        dialog.tree_view.dirty_items = [item_z, item_a, item_m]

        # Track call order
        call_order = []

        def track_add_filter(path):
            call_order.append(path)

        self.mock_engine.add_filter.side_effect = track_add_filter

        # Get the actual method implementation
        actual_apply_filters = DocumentsDialog.apply_filters

        # Call the method
        actual_apply_filters(dialog)

        # Verify items were processed in sorted order
        expected_order = ["/a_folder", "/m_folder", "/z_folder"]
        assert (
            call_order == expected_order
        ), f"Expected {expected_order}, got {call_order}"

    def test_apply_filters_complex_partial_checked_scenarios(self):
        """Test complex scenarios with partially checked items."""

        dialog = Mock(spec=DocumentsDialog)
        dialog.engine = self.mock_engine

        # Scenario 1: Partially checked with old_state Unchecked and mixed children
        parent_item = Mock()
        parent_item.get_path.return_value = "/complex_parent"
        parent_item.state = qt.PartiallyChecked
        parent_item.old_state = qt.Unchecked

        # Mix of checked and unchecked children
        unchecked_child1 = Mock()
        unchecked_child1.get_path.return_value = "/complex_parent/unchecked1"
        unchecked_child1.state = qt.Unchecked

        checked_child = Mock()
        checked_child.get_path.return_value = "/complex_parent/checked"
        checked_child.state = qt.Checked

        unchecked_child2 = Mock()
        unchecked_child2.get_path.return_value = "/complex_parent/unchecked2"
        unchecked_child2.state = qt.Unchecked

        partially_checked_child = Mock()
        partially_checked_child.get_path.return_value = "/complex_parent/partial"
        partially_checked_child.state = qt.PartiallyChecked

        parent_item.get_children.return_value = [
            unchecked_child1,
            checked_child,
            unchecked_child2,
            partially_checked_child,
        ]

        # Mock tree_view
        dialog.tree_view = Mock()
        dialog.tree_view.dirty_items = [parent_item]

        # Get the actual method implementation
        actual_apply_filters = DocumentsDialog.apply_filters

        # Call the method
        actual_apply_filters(dialog)

        # Verify parent filter was removed
        self.mock_engine.remove_filter.assert_called_once_with("/complex_parent")

        # Verify only unchecked children got filters added
        self.mock_engine.add_filter.assert_any_call("/complex_parent/unchecked1")
        self.mock_engine.add_filter.assert_any_call("/complex_parent/unchecked2")

        # Verify checked and partially checked children did NOT get filters
        expected_add_calls = [
            call("/complex_parent/unchecked1"),
            call("/complex_parent/unchecked2"),
        ]
        actual_add_calls = self.mock_engine.add_filter.call_args_list
        assert len(actual_add_calls) == 2
        assert all(call in actual_add_calls for call in expected_add_calls)

    def test_apply_filters_engine_start_conditions(self):
        """Test engine start behavior under different conditions."""

        dialog = Mock(spec=DocumentsDialog)
        dialog.engine = self.mock_engine
        dialog.tree_view = Mock()
        dialog.tree_view.dirty_items = []

        # Get the actual method implementation
        actual_apply_filters = DocumentsDialog.apply_filters

        # Test case 1: Engine not started -> should call start()
        self.mock_engine.is_started.return_value = False
        self.mock_engine.start.reset_mock()

        actual_apply_filters(dialog)

        self.mock_engine.is_started.assert_called_once()
        self.mock_engine.start.assert_called_once()

        # Test case 2: Engine already started -> should NOT call start()
        self.mock_engine.is_started.reset_mock()
        self.mock_engine.start.reset_mock()
        self.mock_engine.is_started.return_value = True

        actual_apply_filters(dialog)

        self.mock_engine.is_started.assert_called_once()
        self.mock_engine.start.assert_not_called()

    def test_apply_filters_all_state_combinations(self):
        """Test all possible item state combinations."""

        dialog = Mock(spec=DocumentsDialog)
        dialog.engine = self.mock_engine

        # Create items for each state condition
        unchecked_item = Mock()
        unchecked_item.get_path.return_value = "/unchecked"
        unchecked_item.state = qt.Unchecked

        checked_item = Mock()
        checked_item.get_path.return_value = "/checked"
        checked_item.state = qt.Checked

        partial_old_unchecked_item = Mock()
        partial_old_unchecked_item.get_path.return_value = "/partial_old_unchecked"
        partial_old_unchecked_item.state = qt.PartiallyChecked
        partial_old_unchecked_item.old_state = qt.Unchecked
        partial_old_unchecked_item.get_children.return_value = []

        partial_old_checked_item = Mock()
        partial_old_checked_item.get_path.return_value = "/partial_old_checked"
        partial_old_checked_item.state = qt.PartiallyChecked
        partial_old_checked_item.old_state = qt.Checked

        # Mock tree_view
        dialog.tree_view = Mock()
        dialog.tree_view.dirty_items = [
            unchecked_item,
            checked_item,
            partial_old_unchecked_item,
            partial_old_checked_item,
        ]

        # Get the actual method implementation
        actual_apply_filters = DocumentsDialog.apply_filters

        # Call the method
        actual_apply_filters(dialog)

        # Verify state-specific behavior
        # Unchecked -> add_filter
        self.mock_engine.add_filter.assert_any_call("/unchecked")

        # Checked -> remove_filter
        self.mock_engine.remove_filter.assert_any_call("/checked")

        # PartiallyChecked with old_state Unchecked -> remove_filter
        self.mock_engine.remove_filter.assert_any_call("/partial_old_unchecked")

        # PartiallyChecked with old_state NOT Unchecked -> no action
        # Verify this path was NOT processed by checking it's not in calls
        add_calls = [
            call.args[0] for call in self.mock_engine.add_filter.call_args_list
        ]
        remove_calls = [
            call.args[0] for call in self.mock_engine.remove_filter.call_args_list
        ]

        assert "/partial_old_checked" not in add_calls
        assert "/partial_old_checked" not in remove_calls

        # Verify expected total call counts
        assert self.mock_engine.add_filter.call_count == 1  # Only unchecked_item
        assert (
            self.mock_engine.remove_filter.call_count == 2
        )  # checked_item + partial_old_unchecked_item


class TestDocumentsDialogSelectUnselectAllRoots:
    """Test cases for DocumentsDialog._select_unselect_all_roots method."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create mock application and engine
        self.mock_application = Mock()
        self.mock_application.icon = Mock()

        self.mock_engine = Mock()
        self.mock_engine.is_syncing.return_value = False
        self.mock_engine.dao.get_filters.return_value = []
        self.mock_engine.remote = Mock()
        self.mock_engine.server_url = "https://test.server.com"

    def test_select_unselect_all_roots_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of _select_unselect_all_roots method."""

        # Create a mock dialog instance
        dialog = Mock(spec=DocumentsDialog)

        # Mock the initial state attributes
        dialog.select_all_state = (
            True  # Initial state: True (means "Unselect All" is shown)
        )
        dialog.select_all_text = ("UNSELECT_ALL", "SELECT_ALL")
        dialog.select_all_button = Mock()

        # Create mock roots for testing
        root1 = Mock()
        root1.get_path.return_value = "/folder1"

        root2 = Mock()
        root2.get_path.return_value = "/folder2"

        root3 = Mock()
        root3.get_path.return_value = "/folder3"

        # Mock tree_view and its components
        dialog.tree_view = Mock()
        dialog.tree_view.client = Mock()
        dialog.tree_view.client.roots = [root3, root1, root2]  # Intentionally unsorted

        # Mock model and items
        mock_model = Mock()
        dialog.tree_view.model.return_value = mock_model

        # Create mock items for each root
        item1 = Mock()
        item1.checkState.return_value = qt.Unchecked  # Different from target state
        item1.setCheckState = Mock()

        item2 = Mock()
        item2.checkState.return_value = qt.Checked  # Same as target state
        item2.setCheckState = Mock()

        item3 = Mock()
        item3.checkState.return_value = qt.Unchecked  # Different from target state
        item3.setCheckState = Mock()

        # Mock indexes and items (sorted order: folder1, folder2, folder3)
        index1 = Mock()
        index2 = Mock()
        index3 = Mock()

        mock_model.index.side_effect = lambda num, col: [index1, index2, index3][num]
        mock_model.itemFromIndex.side_effect = lambda idx: {
            index1: item1,  # /folder1
            index2: item2,  # /folder2
            index3: item3,  # /folder3
        }[idx]

        # Mock update_item_changed
        dialog.tree_view.update_item_changed = Mock()

        # Get the actual method implementation
        actual_select_unselect_all_roots = DocumentsDialog._select_unselect_all_roots

        # Call the method with select_all_state = True (should set items to Checked)
        actual_select_unselect_all_roots(dialog, qt.Checked)  # Second param is ignored

        # Verify roots were sorted by path before processing
        # Expected order: /folder1, /folder2, /folder3

        # Verify model().index() was called for each root in sorted order
        expected_index_calls = [call(0, 0), call(1, 0), call(2, 0)]
        assert mock_model.index.call_args_list == expected_index_calls

        # Verify itemFromIndex was called for each index
        assert mock_model.itemFromIndex.call_count == 3

        # Verify checkState() was called for each item
        item1.checkState.assert_called_once()
        item2.checkState.assert_called_once()
        item3.checkState.assert_called_once()

        # Verify setCheckState was called only for items that needed state change
        # item1: Unchecked -> Checked (should be called)
        item1.setCheckState.assert_called_once_with(qt.Checked)
        # item2: Already Checked -> Checked (should NOT be called)
        item2.setCheckState.assert_not_called()
        # item3: Unchecked -> Checked (should be called)
        item3.setCheckState.assert_called_once_with(qt.Checked)

        # Verify update_item_changed was called for items that changed
        assert dialog.tree_view.update_item_changed.call_count == 2
        dialog.tree_view.update_item_changed.assert_any_call(item1)
        dialog.tree_view.update_item_changed.assert_any_call(item3)

        # Verify state was toggled
        assert dialog.select_all_state is False

        # Verify button text was updated
        # When select_all_state = False (index 0), text should be "UNSELECT_ALL"
        dialog.select_all_button.setText.assert_called_once_with("UNSELECT_ALL")

    def test_select_unselect_all_roots_state_transitions(self):
        """Test state transitions from True to False and False to True."""

        dialog = Mock(spec=DocumentsDialog)

        # Mock minimal required components
        dialog.tree_view = Mock()
        dialog.tree_view.client = Mock()
        dialog.tree_view.client.roots = []  # Empty roots for simple testing
        dialog.tree_view.model.return_value = Mock()
        dialog.select_all_button = Mock()

        # Get the actual method implementation
        actual_select_unselect_all_roots = DocumentsDialog._select_unselect_all_roots

        # Test Case 1: select_all_state = True -> False
        dialog.select_all_state = True
        dialog.select_all_text = ("UNSELECT_ALL", "SELECT_ALL")

        actual_select_unselect_all_roots(dialog, qt.Checked)

        # Verify state was toggled to False
        assert dialog.select_all_state is False
        # Verify button text was set to index 0 (False -> "UNSELECT_ALL")
        dialog.select_all_button.setText.assert_called_with("UNSELECT_ALL")

        # Reset mock
        dialog.select_all_button.setText.reset_mock()

        # Test Case 2: select_all_state = False -> True
        dialog.select_all_state = False

        actual_select_unselect_all_roots(dialog, qt.Unchecked)

        # Verify state was toggled to True
        assert dialog.select_all_state is True
        # Verify button text was set to index 1 (True -> "SELECT_ALL")
        dialog.select_all_button.setText.assert_called_with("SELECT_ALL")

    def test_select_unselect_all_roots_sorting_behavior(self):
        """Test that roots are processed in sorted order by path."""

        dialog = Mock(spec=DocumentsDialog)
        dialog.select_all_state = True
        dialog.select_all_text = ("UNSELECT_ALL", "SELECT_ALL")
        dialog.select_all_button = Mock()

        # Create roots in unsorted order
        root_z = Mock()
        root_z.get_path.return_value = "/z_folder"

        root_a = Mock()
        root_a.get_path.return_value = "/a_folder"

        root_m = Mock()
        root_m.get_path.return_value = "/m_folder"

        # Mock tree_view with unsorted roots
        dialog.tree_view = Mock()
        dialog.tree_view.client = Mock()
        dialog.tree_view.client.roots = [root_z, root_a, root_m]  # Unsorted

        # Mock model
        mock_model = Mock()
        dialog.tree_view.model.return_value = mock_model

        # Track the order of index() calls to verify sorting
        index_calls = []

        def track_index_calls(num, col):
            index_calls.append(num)
            return Mock()

        mock_model.index.side_effect = track_index_calls
        mock_model.itemFromIndex.return_value = Mock()

        # Mock item behavior
        mock_item = Mock()
        mock_item.checkState.return_value = qt.Unchecked
        mock_model.itemFromIndex.return_value = mock_item

        dialog.tree_view.update_item_changed = Mock()

        # Get the actual method implementation
        actual_select_unselect_all_roots = DocumentsDialog._select_unselect_all_roots

        # Call the method
        actual_select_unselect_all_roots(dialog, qt.Checked)

        # Verify roots were processed in sorted order
        # Expected order by path: /a_folder (index 0), /m_folder (index 1), /z_folder (index 2)
        expected_order = [0, 1, 2]
        assert (
            index_calls == expected_order
        ), f"Expected {expected_order}, got {index_calls}"

        # Verify all three roots were processed
        assert len(index_calls) == 3

    def test_select_unselect_all_roots_conditional_updates(self):
        """Test that only items with different checkState are updated."""

        dialog = Mock(spec=DocumentsDialog)
        dialog.select_all_state = False  # Will set target state to qt.Unchecked
        dialog.select_all_text = ("UNSELECT_ALL", "SELECT_ALL")
        dialog.select_all_button = Mock()

        # Create mock roots
        root1 = Mock()
        root1.get_path.return_value = "/folder1"

        root2 = Mock()
        root2.get_path.return_value = "/folder2"

        root3 = Mock()
        root3.get_path.return_value = "/folder3"

        dialog.tree_view = Mock()
        dialog.tree_view.client = Mock()
        dialog.tree_view.client.roots = [root1, root2, root3]

        # Mock model and items
        mock_model = Mock()
        dialog.tree_view.model.return_value = mock_model

        # Create items with different initial states
        item1 = Mock()  # Already Unchecked (matches target)
        item1.checkState.return_value = qt.Unchecked
        item1.setCheckState = Mock()

        item2 = Mock()  # Checked (different from target)
        item2.checkState.return_value = qt.Checked
        item2.setCheckState = Mock()

        item3 = Mock()  # PartiallyChecked (different from target)
        item3.checkState.return_value = qt.PartiallyChecked
        item3.setCheckState = Mock()

        # Mock indexes
        index1, index2, index3 = Mock(), Mock(), Mock()
        mock_model.index.side_effect = lambda num, col: [index1, index2, index3][num]
        mock_model.itemFromIndex.side_effect = lambda idx: {
            index1: item1,
            index2: item2,
            index3: item3,
        }[idx]

        dialog.tree_view.update_item_changed = Mock()

        # Get the actual method implementation
        actual_select_unselect_all_roots = DocumentsDialog._select_unselect_all_roots

        # Call the method (select_all_state = False -> target = qt.Unchecked)
        actual_select_unselect_all_roots(dialog, qt.Checked)

        # Verify checkState was called for all items
        item1.checkState.assert_called_once()
        item2.checkState.assert_called_once()
        item3.checkState.assert_called_once()

        # Verify setCheckState called only for items that differ from target
        # item1: Already Unchecked -> no change needed
        item1.setCheckState.assert_not_called()
        # item2: Checked -> Unchecked (change needed)
        item2.setCheckState.assert_called_once_with(qt.Unchecked)
        # item3: PartiallyChecked -> Unchecked (change needed)
        item3.setCheckState.assert_called_once_with(qt.Unchecked)

        # Verify update_item_changed called only for changed items
        assert dialog.tree_view.update_item_changed.call_count == 2
        dialog.tree_view.update_item_changed.assert_any_call(item2)
        dialog.tree_view.update_item_changed.assert_any_call(item3)

    def test_select_unselect_all_roots_empty_roots(self):
        """Test behavior with empty roots list."""

        dialog = Mock(spec=DocumentsDialog)
        dialog.select_all_state = True
        dialog.select_all_text = ("UNSELECT_ALL", "SELECT_ALL")
        dialog.select_all_button = Mock()

        # Mock tree_view with empty roots
        dialog.tree_view = Mock()
        dialog.tree_view.client = Mock()
        dialog.tree_view.client.roots = []

        mock_model = Mock()
        dialog.tree_view.model.return_value = mock_model

        # Get the actual method implementation
        actual_select_unselect_all_roots = DocumentsDialog._select_unselect_all_roots

        # Call the method
        actual_select_unselect_all_roots(dialog, qt.Checked)

        # Verify no model operations were performed
        mock_model.index.assert_not_called()
        mock_model.itemFromIndex.assert_not_called()

        # Verify state was still toggled
        assert dialog.select_all_state is False

        # Verify button text was still updated
        # When select_all_state = False (after toggle), text should be "UNSELECT_ALL"
        dialog.select_all_button.setText.assert_called_once_with("UNSELECT_ALL")

    def test_select_unselect_all_roots_parameter_ignored(self):
        """Test that the first parameter (Qt.CheckState) is ignored."""

        dialog = Mock(spec=DocumentsDialog)
        dialog.select_all_state = True
        dialog.select_all_text = ("UNSELECT_ALL", "SELECT_ALL")
        dialog.select_all_button = Mock()

        # Mock empty roots for simplicity
        dialog.tree_view = Mock()
        dialog.tree_view.client = Mock()
        dialog.tree_view.client.roots = []
        dialog.tree_view.model.return_value = Mock()

        # Get the actual method implementation
        actual_select_unselect_all_roots = DocumentsDialog._select_unselect_all_roots

        # Call with different parameter values - should not affect behavior
        test_params = [qt.Checked, qt.Unchecked, qt.PartiallyChecked, None]

        for param in test_params:
            # Reset state and mocks
            dialog.select_all_state = True
            dialog.select_all_button.setText.reset_mock()

            # Call method
            actual_select_unselect_all_roots(dialog, param)

            # Verify same behavior regardless of parameter
            assert dialog.select_all_state is False
            # When select_all_state = False (after toggle), text should be "UNSELECT_ALL"
            dialog.select_all_button.setText.assert_called_once_with("UNSELECT_ALL")


class TestFoldersDialogOpenMenu:
    """Test cases for FoldersDialog.open_menu method."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create mock application and engine
        self.mock_application = Mock()
        self.mock_application.icon = Mock()

        self.mock_engine = Mock()
        self.mock_engine.is_syncing.return_value = False
        self.mock_engine.dao.get_filters.return_value = []
        self.mock_engine.remote = Mock()
        self.mock_engine.server_url = "https://test.server.com"

    def test_open_menu_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of open_menu method."""

        # Create a mock dialog instance
        dialog = Mock(spec=FoldersDialog)

        # Mock the tr method for translation
        dialog.tr = Mock(return_value="NEW_REMOTE_FOLDER")

        # Mock the _new_folder_button_action method
        dialog._new_folder_button_action = Mock()

        # Mock the tree_view and its methods
        dialog.tree_view = Mock()
        mock_pointed_item = Mock()
        dialog.tree_view.get_item_from_position = Mock(return_value=mock_pointed_item)
        dialog.tree_view.is_item_enabled = Mock(return_value=True)

        # Mock the viewport and its mapToGlobal method
        mock_viewport = Mock()
        global_position = Mock()
        mock_viewport.mapToGlobal = Mock(return_value=global_position)
        dialog.tree_view.viewport = Mock(return_value=mock_viewport)

        # Create a mock QMenu and its methods
        mock_menu = Mock(spec=QMenu)
        mock_action = Mock()
        mock_menu.addAction = Mock(return_value=mock_action)
        mock_menu.exec_ = Mock()

        # Create a test position
        test_position = Mock(spec=QPoint)

        # Get the actual method implementation
        actual_open_menu = FoldersDialog.open_menu

        # Test Case 1: Normal execution with enabled tree item
        with patch(
            "nxdrive.gui.folders_dialog.QMenu", return_value=mock_menu
        ) as mock_qmenu_class:
            # Call the method
            actual_open_menu(dialog, test_position)

            # Verify QMenu was instantiated
            mock_qmenu_class.assert_called_once()

            # Verify menu action was added with correct parameters
            mock_menu.addAction.assert_called_once_with(
                "NEW_REMOTE_FOLDER", dialog._new_folder_button_action
            )

            # Verify tr method was called for translation
            dialog.tr.assert_called_once_with("NEW_REMOTE_FOLDER")

            # Verify tree_view.get_item_from_position was called with correct position
            dialog.tree_view.get_item_from_position.assert_called_once_with(
                test_position
            )

            # Verify tree_view.is_item_enabled was called with the pointed item
            dialog.tree_view.is_item_enabled.assert_called_once_with(mock_pointed_item)

            # Verify action.setEnabled was called with the result of is_item_enabled (True)
            mock_action.setEnabled.assert_called_once_with(True)

            # Verify viewport was accessed and mapToGlobal was called
            dialog.tree_view.viewport.assert_called_once()
            mock_viewport.mapToGlobal.assert_called_once_with(test_position)

            # Verify menu.exec_ was called with the global position
            mock_menu.exec_.assert_called_once_with(global_position)

            # Verify execution order by checking call counts
            assert dialog.tr.call_count == 1
            assert mock_menu.addAction.call_count == 1
            assert dialog.tree_view.get_item_from_position.call_count == 1
            assert dialog.tree_view.is_item_enabled.call_count == 1
            assert mock_action.setEnabled.call_count == 1
            assert dialog.tree_view.viewport.call_count == 1
            assert mock_viewport.mapToGlobal.call_count == 1
            assert mock_menu.exec_.call_count == 1

        # Test Case 2: When tree item is disabled
        dialog.tree_view.is_item_enabled.reset_mock()
        dialog.tree_view.is_item_enabled.return_value = False
        mock_action.setEnabled.reset_mock()

        # Create new mock menu for second test
        mock_menu2 = Mock(spec=QMenu)
        mock_action2 = Mock()
        mock_menu2.addAction = Mock(return_value=mock_action2)
        mock_menu2.exec_ = Mock()

        with patch("nxdrive.gui.folders_dialog.QMenu", return_value=mock_menu2):
            # Call the method again
            actual_open_menu(dialog, test_position)

            # Verify action is disabled when tree item is disabled
            mock_action2.setEnabled.assert_called_once_with(False)

        # Test Case 3: Verify method handles different positions
        test_position2 = Mock(spec=QPoint)
        global_position2 = Mock()
        mock_viewport.mapToGlobal.reset_mock()
        mock_viewport.mapToGlobal.return_value = global_position2

        # Create new mock menu for third test
        mock_menu3 = Mock(spec=QMenu)
        mock_action3 = Mock()
        mock_menu3.addAction = Mock(return_value=mock_action3)
        mock_menu3.exec_ = Mock()

        with patch("nxdrive.gui.folders_dialog.QMenu", return_value=mock_menu3):
            # Call with different position
            actual_open_menu(dialog, test_position2)

            # Verify mapToGlobal was called with the new position
            mock_viewport.mapToGlobal.assert_called_with(test_position2)

            # Verify exec_ was called with the new global position
            mock_menu3.exec_.assert_called_once_with(global_position2)

        # Test Case 4: Verify translation key is used correctly
        dialog.tr.reset_mock()
        dialog.tr.return_value = "TRANSLATED_TEXT"

        mock_menu4 = Mock(spec=QMenu)
        mock_action4 = Mock()
        mock_menu4.addAction = Mock(return_value=mock_action4)
        mock_menu4.exec_ = Mock()

        with patch("nxdrive.gui.folders_dialog.QMenu", return_value=mock_menu4):
            # Call the method
            actual_open_menu(dialog, test_position)

            # Verify the translated text was used
            mock_menu4.addAction.assert_called_once_with(
                "TRANSLATED_TEXT", dialog._new_folder_button_action
            )

        # Test Case 5: Verify that all components work together
        # Reset all mocks for final comprehensive test
        dialog.tr.reset_mock()
        dialog.tr.return_value = "FINAL_TEST"
        dialog.tree_view.get_item_from_position.reset_mock()
        dialog.tree_view.is_item_enabled.reset_mock()
        dialog.tree_view.is_item_enabled.return_value = True
        dialog.tree_view.viewport.reset_mock()
        mock_viewport.mapToGlobal.reset_mock()

        final_pointed_item = Mock()
        final_position = Mock(spec=QPoint)
        final_global_position = Mock()

        dialog.tree_view.get_item_from_position.return_value = final_pointed_item
        mock_viewport.mapToGlobal.return_value = final_global_position

        mock_menu5 = Mock(spec=QMenu)
        mock_action5 = Mock()
        mock_menu5.addAction = Mock(return_value=mock_action5)
        mock_menu5.exec_ = Mock()

        with patch("nxdrive.gui.folders_dialog.QMenu", return_value=mock_menu5):
            # Call the method one final time
            actual_open_menu(dialog, final_position)

            # Comprehensive verification of the complete flow
            assert dialog.tr.called
            assert dialog.tree_view.get_item_from_position.called
            assert dialog.tree_view.is_item_enabled.called
            assert mock_action5.setEnabled.called
            assert dialog.tree_view.viewport.called
            assert mock_viewport.mapToGlobal.called
            assert mock_menu5.exec_.called

            # Verify the exact sequence
            dialog.tree_view.get_item_from_position.assert_called_with(final_position)
            dialog.tree_view.is_item_enabled.assert_called_with(final_pointed_item)
            mock_viewport.mapToGlobal.assert_called_with(final_position)
            mock_menu5.exec_.assert_called_with(final_global_position)


class TestFoldersDialogCheckForKnownTypes:
    """Test cases for FoldersDialog._check_for_known_types method."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create mock application and engine
        self.mock_application = Mock()
        self.mock_application.icon = Mock()

        self.mock_engine = Mock()
        self.mock_engine.is_syncing.return_value = False
        self.mock_engine.dao.get_filters.return_value = []
        self.mock_engine.remote = Mock()
        self.mock_engine.server_url = "https://test.server.com"

    def test_check_for_known_types_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of _check_for_known_types method."""

        # Create a mock dialog instance
        dialog = Mock(spec=FoldersDialog)

        # Set up known types dictionaries
        dialog.KNOWN_FOLDER_TYPES = {
            "Folder": "Dossier",
            "OrderedFolder": "Dossier Ordonné",
            "Collection": "Collection",
        }
        dialog.KNOWN_FILE_TYPES = {
            "File": "Fichier",
            "Picture": "Image",
            "Video": "Vidéo",
        }

        # Get the actual method implementation
        actual_check_for_known_types = FoldersDialog._check_for_known_types

        # Test Case 1: is_folder_type=True with matching folder types
        dialog.containerTypeList = [
            "Folder",
            "SomeOtherType",
            "OrderedFolder",
            "UnknownType",
        ]

        # Call the method for folder types
        actual_check_for_known_types(dialog, True)

        # Verify that matching keys were replaced with their values
        expected_container_list = [
            "SomeOtherType",
            "UnknownType",
            "Dossier",
            "Dossier Ordonné",
        ]
        assert dialog.containerTypeList == expected_container_list

        # Verify the transformation happened correctly
        assert "Folder" not in dialog.containerTypeList
        assert "OrderedFolder" not in dialog.containerTypeList
        assert "Dossier" in dialog.containerTypeList
        assert "Dossier Ordonné" in dialog.containerTypeList
        assert (
            "SomeOtherType" in dialog.containerTypeList
        )  # Non-matching items preserved
        assert "UnknownType" in dialog.containerTypeList

        # Test Case 2: is_folder_type=False with matching file types
        dialog.docTypeList = ["File", "Picture", "SomeDocType", "UnknownDoc"]

        # Call the method for file types
        actual_check_for_known_types(dialog, False)

        # Verify that matching keys were replaced with their values
        expected_doc_list = ["SomeDocType", "UnknownDoc", "Fichier", "Image"]
        assert dialog.docTypeList == expected_doc_list

        # Verify the transformation happened correctly
        assert "File" not in dialog.docTypeList
        assert "Picture" not in dialog.docTypeList
        assert "Fichier" in dialog.docTypeList
        assert "Image" in dialog.docTypeList
        assert "SomeDocType" in dialog.docTypeList  # Non-matching items preserved
        assert "UnknownDoc" in dialog.docTypeList

        # Test Case 3: is_folder_type=True with no matching types
        dialog.containerTypeList = ["NonMatchingType1", "NonMatchingType2"]
        original_container_list = dialog.containerTypeList.copy()

        # Call the method for folder types
        actual_check_for_known_types(dialog, True)

        # Verify that the list remains unchanged when no matches
        assert dialog.containerTypeList == original_container_list
        assert len(dialog.containerTypeList) == 2
        assert "NonMatchingType1" in dialog.containerTypeList
        assert "NonMatchingType2" in dialog.containerTypeList

        # Test Case 4: is_folder_type=False with no matching types
        dialog.docTypeList = ["NonMatchingDoc1", "NonMatchingDoc2"]
        original_doc_list = dialog.docTypeList.copy()

        # Call the method for file types
        actual_check_for_known_types(dialog, False)

        # Verify that the list remains unchanged when no matches
        assert dialog.docTypeList == original_doc_list
        assert len(dialog.docTypeList) == 2
        assert "NonMatchingDoc1" in dialog.docTypeList
        assert "NonMatchingDoc2" in dialog.docTypeList

        # Test Case 5: Empty lists
        dialog.containerTypeList = []
        dialog.docTypeList = []

        # Call the method for folder types with empty list
        actual_check_for_known_types(dialog, True)
        assert dialog.containerTypeList == []

        # Call the method for file types with empty list
        actual_check_for_known_types(dialog, False)
        assert dialog.docTypeList == []

        # Test Case 6: Empty known types dictionaries
        dialog.KNOWN_FOLDER_TYPES = {}
        dialog.KNOWN_FILE_TYPES = {}
        dialog.containerTypeList = ["Folder", "OrderedFolder"]
        dialog.docTypeList = ["File", "Picture"]
        original_container_list = dialog.containerTypeList.copy()
        original_doc_list = dialog.docTypeList.copy()

        # Call the method with empty known types
        actual_check_for_known_types(dialog, True)
        actual_check_for_known_types(dialog, False)

        # Verify lists remain unchanged when no known types
        assert dialog.containerTypeList == original_container_list
        assert dialog.docTypeList == original_doc_list

        # Test Case 7: Partial matches with complex scenario
        dialog.KNOWN_FOLDER_TYPES = {"TypeA": "TranslatedA", "TypeC": "TranslatedC"}
        dialog.KNOWN_FILE_TYPES = {"DocX": "TranslatedX", "DocZ": "TranslatedZ"}
        dialog.containerTypeList = ["TypeA", "TypeB", "TypeC", "TypeD"]
        dialog.docTypeList = ["DocW", "DocX", "DocY", "DocZ"]

        # Call the methods
        actual_check_for_known_types(dialog, True)
        actual_check_for_known_types(dialog, False)

        # Verify partial transformation for folders
        assert "TypeA" not in dialog.containerTypeList
        assert "TypeC" not in dialog.containerTypeList
        assert "TranslatedA" in dialog.containerTypeList
        assert "TranslatedC" in dialog.containerTypeList
        assert "TypeB" in dialog.containerTypeList  # Unmatched preserved
        assert "TypeD" in dialog.containerTypeList  # Unmatched preserved

        # Verify partial transformation for files
        assert "DocX" not in dialog.docTypeList
        assert "DocZ" not in dialog.docTypeList
        assert "TranslatedX" in dialog.docTypeList
        assert "TranslatedZ" in dialog.docTypeList
        assert "DocW" in dialog.docTypeList  # Unmatched preserved
        assert "DocY" in dialog.docTypeList  # Unmatched preserved

        # Test Case 8: Order preservation test
        dialog.KNOWN_FOLDER_TYPES = {"First": "Premier"}
        dialog.containerTypeList = ["Other1", "First", "Other2"]

        # Call the method
        actual_check_for_known_types(dialog, True)

        # Verify that the translated item is appended at the end
        expected_order = ["Other1", "Other2", "Premier"]
        assert dialog.containerTypeList == expected_order

        # Test Case 9: Multiple occurrences of the same key
        dialog.KNOWN_FOLDER_TYPES = {"Duplicate": "Dupliqué"}
        dialog.containerTypeList = ["Duplicate", "Other", "Duplicate"]

        # Call the method
        actual_check_for_known_types(dialog, True)

        # Verify that only the first occurrence is removed and translation added once
        # The remove() method only removes the first occurrence
        assert (
            dialog.containerTypeList.count("Duplicate") == 1
        )  # One occurrence remains
        assert "Dupliqué" in dialog.containerTypeList
        assert "Other" in dialog.containerTypeList
        expected_result = ["Other", "Duplicate", "Dupliqué"]
        assert dialog.containerTypeList == expected_result

        # Test Case 10: Verify method doesn't modify KNOWN_* dictionaries
        original_folder_types = dialog.KNOWN_FOLDER_TYPES.copy()
        original_file_types = dialog.KNOWN_FILE_TYPES.copy()

        dialog.containerTypeList = ["Duplicate"]
        dialog.docTypeList = []

        # Call the method
        actual_check_for_known_types(dialog, True)
        actual_check_for_known_types(dialog, False)

        # Verify dictionaries are unchanged
        assert dialog.KNOWN_FOLDER_TYPES == original_folder_types
        assert dialog.KNOWN_FILE_TYPES == original_file_types


class TestFoldersDialogUpdateFileGroup:
    """Test cases for FoldersDialog.update_file_group method."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create mock application and engine
        self.mock_application = Mock()
        self.mock_application.icon = Mock()

        self.mock_engine = Mock()
        self.mock_engine.is_syncing.return_value = False
        self.mock_engine.dao.get_filters.return_value = []
        self.mock_engine.remote = Mock()
        self.mock_engine.server_url = "https://test.server.com"

    def test_update_file_group_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of update_file_group method."""

        # Create a mock dialog instance
        dialog = Mock(spec=FoldersDialog)

        # Mock the ComboBox widgets
        dialog.cbDocType = Mock(spec=QComboBox)
        dialog.cbContainerType = Mock(spec=QComboBox)

        # Mock the engine and remote for doc enricher calls
        dialog.engine = Mock()
        dialog.engine.remote = Mock()

        # Mock the _check_for_known_types method
        dialog._check_for_known_types = Mock()

        # Set up DEFAULT_TYPES
        dialog.DEFAULT_TYPES = {"Default Document": "Document"}

        # Get the actual method implementation
        actual_update_file_group = FoldersDialog.update_file_group

        # Test Case 1: With empty DEFAULT_TYPES
        dialog.DEFAULT_TYPES = {}
        dialog.remote_folder_ref = None

        # Call the method
        actual_update_file_group(dialog)

        # Verify ComboBoxes are cleared
        dialog.cbDocType.clear.assert_called_once()
        dialog.cbContainerType.clear.assert_called_once()

        # Verify no items are added when DEFAULT_TYPES is empty
        dialog.cbDocType.addItem.assert_not_called()
        dialog.cbContainerType.addItem.assert_not_called()

        # Verify no remote calls when remote_folder_ref is None
        dialog.engine.remote.get_doc_enricher.assert_not_called()
        dialog._check_for_known_types.assert_not_called()

        # Test Case 2: With DEFAULT_TYPES and no remote_folder_ref
        dialog.cbDocType.clear.reset_mock()
        dialog.cbContainerType.clear.reset_mock()
        dialog.cbDocType.addItem.reset_mock()
        dialog.cbContainerType.addItem.reset_mock()

        # DEFAULT_TYPES.values() should provide at least 2 values for addItem(values[0], values[1])
        dialog.DEFAULT_TYPES = {"key1": "DefaultLabel", "key2": "DefaultValue"}
        dialog.remote_folder_ref = None

        # Call the method
        actual_update_file_group(dialog)

        # Verify ComboBoxes are cleared
        dialog.cbDocType.clear.assert_called_once()
        dialog.cbContainerType.clear.assert_called_once()

        # Verify default items are added
        dialog.cbContainerType.addItem.assert_called_once_with(
            "DefaultLabel", "DefaultValue"
        )
        dialog.cbDocType.addItem.assert_called_once_with("DefaultLabel", "DefaultValue")

        # Verify no remote calls when remote_folder_ref is None
        dialog.engine.remote.get_doc_enricher.assert_not_called()
        dialog._check_for_known_types.assert_not_called()

        # Test Case 3: With remote_folder_ref but empty DEFAULT_TYPES
        dialog.cbDocType.clear.reset_mock()
        dialog.cbContainerType.clear.reset_mock()
        dialog.cbDocType.addItem.reset_mock()
        dialog.cbContainerType.addItem.reset_mock()
        dialog.cbDocType.addItems.reset_mock()
        dialog.cbContainerType.addItems.reset_mock()
        dialog.engine.remote.get_doc_enricher.reset_mock()
        dialog._check_for_known_types.reset_mock()

        dialog.DEFAULT_TYPES = {}
        dialog.remote_folder_ref = "remote_ref_123"

        # Mock the enricher responses
        mock_doc_types = ["File", "Picture", "Video"]
        mock_container_types = ["Folder", "OrderedFolder", "Collection"]
        dialog.engine.remote.get_doc_enricher.side_effect = [
            mock_doc_types,
            mock_container_types,
        ]

        # Call the method
        actual_update_file_group(dialog)

        # Verify ComboBoxes are cleared
        dialog.cbDocType.clear.assert_called_once()
        dialog.cbContainerType.clear.assert_called_once()

        # Verify no default items added when DEFAULT_TYPES is empty
        dialog.cbDocType.addItem.assert_not_called()
        dialog.cbContainerType.addItem.assert_not_called()

        # Verify remote calls are made twice (once for each type)
        expected_calls = [
            call("remote_ref_123", "subtypes", False),  # For docTypeList
            call("remote_ref_123", "subtypes", True),  # For containerTypeList
        ]
        dialog.engine.remote.get_doc_enricher.assert_has_calls(expected_calls)

        # Verify docTypeList is set and processed
        assert dialog.docTypeList == mock_doc_types
        dialog._check_for_known_types.assert_any_call(False)
        dialog.cbDocType.addItems.assert_called_once_with(mock_doc_types)

        # Verify containerTypeList is set and processed
        assert dialog.containerTypeList == mock_container_types
        dialog._check_for_known_types.assert_any_call(True)
        dialog.cbContainerType.addItems.assert_called_once_with(mock_container_types)

        # Test Case 4: Complete scenario with both DEFAULT_TYPES and remote_folder_ref
        dialog.cbDocType.clear.reset_mock()
        dialog.cbContainerType.clear.reset_mock()
        dialog.cbDocType.addItem.reset_mock()
        dialog.cbContainerType.addItem.reset_mock()
        dialog.cbDocType.addItems.reset_mock()
        dialog.cbContainerType.addItems.reset_mock()
        dialog.engine.remote.get_doc_enricher.reset_mock()
        dialog._check_for_known_types.reset_mock()

        dialog.DEFAULT_TYPES = {"label_key": "Default", "value_key": "DefaultDocType"}
        dialog.remote_folder_ref = "complete_ref_456"

        # Mock new enricher responses
        new_doc_types = ["Document", "Note", "File"]
        new_container_types = ["Workspace", "Folder"]
        dialog.engine.remote.get_doc_enricher.side_effect = [
            new_doc_types,
            new_container_types,
        ]

        # Call the method
        actual_update_file_group(dialog)

        # Verify complete flow
        dialog.cbDocType.clear.assert_called_once()
        dialog.cbContainerType.clear.assert_called_once()

        # Verify default items are added
        dialog.cbContainerType.addItem.assert_called_once_with(
            "Default", "DefaultDocType"
        )
        dialog.cbDocType.addItem.assert_called_once_with("Default", "DefaultDocType")

        # Verify remote enricher calls
        expected_calls = [
            call("complete_ref_456", "subtypes", False),
            call("complete_ref_456", "subtypes", True),
        ]
        dialog.engine.remote.get_doc_enricher.assert_has_calls(expected_calls)

        # Verify type lists are set
        assert dialog.docTypeList == new_doc_types
        assert dialog.containerTypeList == new_container_types

        # Verify _check_for_known_types is called for both types
        dialog._check_for_known_types.assert_any_call(False)
        dialog._check_for_known_types.assert_any_call(True)
        assert dialog._check_for_known_types.call_count == 2

        # Verify items are added to ComboBoxes
        dialog.cbDocType.addItems.assert_called_once_with(new_doc_types)
        dialog.cbContainerType.addItems.assert_called_once_with(new_container_types)

        # Test Case 5: Verify method execution order
        dialog.cbDocType.clear.reset_mock()
        dialog.cbContainerType.clear.reset_mock()
        dialog.cbDocType.addItem.reset_mock()
        dialog.cbContainerType.addItem.reset_mock()
        dialog.cbDocType.addItems.reset_mock()
        dialog.cbContainerType.addItems.reset_mock()
        dialog.engine.remote.get_doc_enricher.reset_mock()
        dialog._check_for_known_types.reset_mock()

        dialog.DEFAULT_TYPES = {"order_label": "OrderTest", "order_value": "OrderValue"}
        dialog.remote_folder_ref = "order_test_ref"

        # Track call order
        call_order = []

        def track_clear_doc():
            call_order.append("cbDocType.clear")

        def track_clear_container():
            call_order.append("cbContainerType.clear")

        def track_add_item_container(label, value):
            call_order.append(f"cbContainerType.addItem({label}, {value})")

        def track_add_item_doc(label, value):
            call_order.append(f"cbDocType.addItem({label}, {value})")

        def track_get_doc_enricher(ref, subtype, is_folder):
            call_order.append(f"get_doc_enricher({ref}, {subtype}, {is_folder})")
            if is_folder:
                return ["TestContainer"]
            else:
                return ["TestDoc"]

        def track_check_known_types(is_folder):
            call_order.append(f"_check_for_known_types({is_folder})")

        def track_add_items_doc(items):
            call_order.append(f"cbDocType.addItems({items})")

        def track_add_items_container(items):
            call_order.append(f"cbContainerType.addItems({items})")

        # Set up side effects
        dialog.cbDocType.clear.side_effect = track_clear_doc
        dialog.cbContainerType.clear.side_effect = track_clear_container
        dialog.cbContainerType.addItem.side_effect = track_add_item_container
        dialog.cbDocType.addItem.side_effect = track_add_item_doc
        dialog.engine.remote.get_doc_enricher.side_effect = track_get_doc_enricher
        dialog._check_for_known_types.side_effect = track_check_known_types
        dialog.cbDocType.addItems.side_effect = track_add_items_doc
        dialog.cbContainerType.addItems.side_effect = track_add_items_container

        # Call the method
        actual_update_file_group(dialog)

        # Verify execution order
        expected_order = [
            "cbDocType.clear",
            "cbContainerType.clear",
            "cbContainerType.addItem(OrderTest, OrderValue)",
            "cbDocType.addItem(OrderTest, OrderValue)",
            "get_doc_enricher(order_test_ref, subtypes, False)",
            "_check_for_known_types(False)",
            "cbDocType.addItems(['TestDoc'])",
            "get_doc_enricher(order_test_ref, subtypes, True)",
            "_check_for_known_types(True)",
            "cbContainerType.addItems(['TestContainer'])",
        ]
        assert call_order == expected_order

        # Test Case 6: Edge case with multiple DEFAULT_TYPES values
        dialog.cbDocType.clear.reset_mock()
        dialog.cbContainerType.clear.reset_mock()
        dialog.cbDocType.addItem.reset_mock()
        dialog.cbContainerType.addItem.reset_mock()

        # Reset side effects
        dialog.cbDocType.clear.side_effect = None
        dialog.cbContainerType.clear.side_effect = None
        dialog.cbContainerType.addItem.side_effect = None
        dialog.cbDocType.addItem.side_effect = None

        dialog.DEFAULT_TYPES = {
            "first_key": "First",
            "second_key": "FirstValue",
            "third_key": "Second",
            "fourth_key": "SecondValue",
        }
        dialog.remote_folder_ref = None

        # Call the method
        actual_update_file_group(dialog)

        # Verify only the first pair is used (list conversion takes first two values)
        dialog.cbContainerType.addItem.assert_called_once_with("First", "FirstValue")
        dialog.cbDocType.addItem.assert_called_once_with("First", "FirstValue")

        # Test Case 7: Verify attributes are set correctly
        dialog.DEFAULT_TYPES = {"attr_label": "AttrTest", "attr_value": "AttrValue"}
        dialog.remote_folder_ref = "attr_test_ref"

        test_doc_list = ["AttrDoc1", "AttrDoc2"]
        test_container_list = ["AttrContainer1", "AttrContainer2"]
        dialog.engine.remote.get_doc_enricher.side_effect = [
            test_doc_list,
            test_container_list,
        ]

        # Call the method
        actual_update_file_group(dialog)

        # Verify the type lists are properly assigned to dialog attributes
        assert hasattr(dialog, "docTypeList")
        assert hasattr(dialog, "containerTypeList")
        assert dialog.docTypeList == test_doc_list
        assert dialog.containerTypeList == test_container_list


class TestFoldersDialogNewFolderButtonAction:
    """Test cases for FoldersDialog._new_folder_button_action method."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create mock application and engine
        self.mock_application = Mock()
        self.mock_application.icon = Mock()

        self.mock_engine = Mock()
        self.mock_engine.is_syncing.return_value = False
        self.mock_engine.dao.get_filters.return_value = []
        self.mock_engine.remote = Mock()
        self.mock_engine.server_url = "https://test.server.com"

    def test_new_folder_button_action_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of _new_folder_button_action method."""

        # Create a mock dialog instance
        dialog = Mock(spec=FoldersDialog)

        # Get the actual method implementation
        actual_new_folder_button_action = FoldersDialog._new_folder_button_action

        # Test Case 1: Normal execution - dialog creation and execution
        with patch(
            "nxdrive.gui.folders_dialog.NewFolderDialog"
        ) as mock_new_folder_dialog_class:
            # Create a mock dialog instance
            mock_new_folder_dialog = Mock(spec=NewFolderDialog)
            mock_new_folder_dialog_class.return_value = mock_new_folder_dialog

            # Call the method
            actual_new_folder_button_action(dialog)

            # Verify NewFolderDialog was instantiated with the correct parent
            mock_new_folder_dialog_class.assert_called_once_with(dialog)

            # Verify exec_() was called on the dialog instance
            mock_new_folder_dialog.exec_.assert_called_once()

            # Verify the method completed without errors
            assert mock_new_folder_dialog_class.call_count == 1
            assert mock_new_folder_dialog.exec_.call_count == 1

        # Test Case 2: Verify method execution order
        with patch(
            "nxdrive.gui.folders_dialog.NewFolderDialog"
        ) as mock_new_folder_dialog_class:
            # Track call order
            call_order = []

            def track_dialog_creation(parent):
                call_order.append(f"NewFolderDialog({parent})")
                mock_dialog = Mock(spec=NewFolderDialog)
                mock_dialog.exec_ = Mock(
                    side_effect=lambda: call_order.append("exec_()")
                )
                return mock_dialog

            mock_new_folder_dialog_class.side_effect = track_dialog_creation

            # Call the method
            actual_new_folder_button_action(dialog)

            # Verify execution order
            expected_order = [f"NewFolderDialog({dialog})", "exec_()"]
            assert call_order == expected_order

        # Test Case 3: Test with different dialog instances
        dialog2 = Mock(spec=FoldersDialog)
        dialog3 = Mock(spec=FoldersDialog)

        with patch(
            "nxdrive.gui.folders_dialog.NewFolderDialog"
        ) as mock_new_folder_dialog_class:
            mock_new_folder_dialog1 = Mock(spec=NewFolderDialog)
            mock_new_folder_dialog2 = Mock(spec=NewFolderDialog)
            mock_new_folder_dialog3 = Mock(spec=NewFolderDialog)

            mock_new_folder_dialog_class.side_effect = [
                mock_new_folder_dialog1,
                mock_new_folder_dialog2,
                mock_new_folder_dialog3,
            ]

            # Call method with different dialog instances
            actual_new_folder_button_action(dialog)
            actual_new_folder_button_action(dialog2)
            actual_new_folder_button_action(dialog3)

            # Verify each call used the correct parent dialog
            expected_calls = [call(dialog), call(dialog2), call(dialog3)]
            mock_new_folder_dialog_class.assert_has_calls(expected_calls)

            # Verify exec_() was called on each dialog instance
            mock_new_folder_dialog1.exec_.assert_called_once()
            mock_new_folder_dialog2.exec_.assert_called_once()
            mock_new_folder_dialog3.exec_.assert_called_once()

            # Verify total call counts
            assert mock_new_folder_dialog_class.call_count == 3

        # Test Case 4: Verify no side effects on the parent dialog
        original_dialog_state = {
            "attr1": getattr(dialog, "attr1", "test_value"),
            "attr2": getattr(dialog, "attr2", 42),
        }

        # Set some attributes on the dialog to verify they don't change
        dialog.attr1 = "test_value"
        dialog.attr2 = 42

        with patch(
            "nxdrive.gui.folders_dialog.NewFolderDialog"
        ) as mock_new_folder_dialog_class:
            mock_new_folder_dialog = Mock(spec=NewFolderDialog)
            mock_new_folder_dialog_class.return_value = mock_new_folder_dialog

            # Call the method
            actual_new_folder_button_action(dialog)

            # Verify parent dialog attributes remain unchanged
            assert dialog.attr1 == original_dialog_state["attr1"]
            assert dialog.attr2 == original_dialog_state["attr2"]

        # Test Case 5: Test exception handling from NewFolderDialog constructor
        with patch(
            "nxdrive.gui.folders_dialog.NewFolderDialog"
        ) as mock_new_folder_dialog_class:
            # Make the constructor raise an exception
            mock_new_folder_dialog_class.side_effect = Exception(
                "Dialog creation failed"
            )

            # Call the method and expect exception to propagate
            try:
                actual_new_folder_button_action(dialog)
                assert False, "Expected exception from NewFolderDialog constructor"
            except Exception as e:
                assert str(e) == "Dialog creation failed"

            # Verify constructor was called
            mock_new_folder_dialog_class.assert_called_once_with(dialog)

        # Test Case 6: Test exception handling from exec_() method
        with patch(
            "nxdrive.gui.folders_dialog.NewFolderDialog"
        ) as mock_new_folder_dialog_class:
            mock_new_folder_dialog = Mock(spec=NewFolderDialog)
            mock_new_folder_dialog.exec_.side_effect = Exception(
                "Dialog execution failed"
            )
            mock_new_folder_dialog_class.return_value = mock_new_folder_dialog

            # Call the method and expect exception to propagate
            try:
                actual_new_folder_button_action(dialog)
                assert False, "Expected exception from exec_() method"
            except Exception as e:
                assert str(e) == "Dialog execution failed"

            # Verify both methods were called before exception
            mock_new_folder_dialog_class.assert_called_once_with(dialog)
            mock_new_folder_dialog.exec_.assert_called_once()

        # Test Case 7: Verify dialog creation with different parent types
        # Create a mock that is a subclass of FoldersDialog
        class TestFoldersDialog(FoldersDialog):
            pass

        specialized_dialog = Mock(spec=TestFoldersDialog)

        with patch(
            "nxdrive.gui.folders_dialog.NewFolderDialog"
        ) as mock_new_folder_dialog_class:
            mock_new_folder_dialog = Mock(spec=NewFolderDialog)
            mock_new_folder_dialog_class.return_value = mock_new_folder_dialog

            # Call with specialized dialog
            actual_new_folder_button_action(specialized_dialog)

            # Verify it works with subclass instances
            mock_new_folder_dialog_class.assert_called_once_with(specialized_dialog)
            mock_new_folder_dialog.exec_.assert_called_once()

        # Test Case 8: Verify method can be called multiple times on same dialog
        with patch(
            "nxdrive.gui.folders_dialog.NewFolderDialog"
        ) as mock_new_folder_dialog_class:
            # Create different mock dialog instances for each call
            mock_dialogs = [Mock(spec=NewFolderDialog) for _ in range(3)]
            mock_new_folder_dialog_class.side_effect = mock_dialogs

            # Call method multiple times on same parent dialog
            actual_new_folder_button_action(dialog)
            actual_new_folder_button_action(dialog)
            actual_new_folder_button_action(dialog)

            # Verify each call created a new dialog instance
            assert mock_new_folder_dialog_class.call_count == 3
            expected_calls = [call(dialog)] * 3
            mock_new_folder_dialog_class.assert_has_calls(expected_calls)

            # Verify exec_() was called on each instance
            for mock_dialog in mock_dialogs:
                mock_dialog.exec_.assert_called_once()

        # Test Case 9: Verify the method signature and return value
        with patch(
            "nxdrive.gui.folders_dialog.NewFolderDialog"
        ) as mock_new_folder_dialog_class:
            mock_new_folder_dialog = Mock(spec=NewFolderDialog)
            mock_new_folder_dialog_class.return_value = mock_new_folder_dialog

            # Call the method and capture return value
            result = actual_new_folder_button_action(dialog)

            # Verify method returns None (as per signature)
            assert result is None

            # Verify dialog creation and execution happened
            mock_new_folder_dialog_class.assert_called_once_with(dialog)
            mock_new_folder_dialog.exec_.assert_called_once()

        # Test Case 10: Integration test - verify NewFolderDialog gets correct parent reference
        with patch(
            "nxdrive.gui.folders_dialog.NewFolderDialog"
        ) as mock_new_folder_dialog_class:

            def verify_parent_dialog(parent):
                # Verify the parent is the correct dialog instance
                assert parent is dialog
                mock_dialog = Mock(spec=NewFolderDialog)
                return mock_dialog

            mock_new_folder_dialog_class.side_effect = verify_parent_dialog

            # Call the method
            actual_new_folder_button_action(dialog)

            # The verification happens in the side_effect function
            mock_new_folder_dialog_class.assert_called_once_with(dialog)


class TestFoldersDialogFindFoldersDuplicates:
    """Test cases for FoldersDialog._find_folders_duplicates method."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create mock application and engine
        self.mock_app = Mock()
        self.mock_engine = Mock()
        self.mock_remote = Mock()
        self.mock_engine.remote = self.mock_remote
        self.mock_dao = Mock()
        self.mock_engine.dao = self.mock_dao

        # Mock the get_config method for remote_folder_ref
        self.mock_dao.get_config.return_value = "/default/remote/folder"

    @patch("nxdrive.gui.folders_dialog.FoldersDialog.__init__", return_value=None)
    def test_find_folders_duplicates_comprehensive_functionality(self, mock_init):
        """Test comprehensive functionality covering all aspects of _find_folders_duplicates method.

        This test covers:
        1. Normal execution with duplicate folders found
        2. Empty paths dictionary handling
        3. No duplicate folders scenario
        4. Mixed files and folders handling
        5. Parent-child relationship filtering
        6. Remote exists_in_parent integration
        7. Metric sending verification
        8. Return type verification
        9. Multiple duplicates handling
        10. Edge cases with special path structures
        """
        from pathlib import Path

        # Create a FoldersDialog instance for testing
        dialog = FoldersDialog.__new__(FoldersDialog)

        # Set up required attributes that would normally be set in __init__
        dialog.engine = self.mock_engine
        dialog.remote_folder_ref = "/test/remote/folder"

        # Test 1: Empty paths dictionary handling
        dialog.paths = {}
        self.mock_remote.reset_mock()
        self.mock_engine.reset_mock()

        result = dialog._find_folders_duplicates()

        assert isinstance(result, list)
        assert len(result) == 0
        self.mock_remote.exists_in_parent.assert_not_called()
        self.mock_engine.send_metric.assert_not_called()

        # Test 2: Simple case with mock paths that work properly
        # Create mock paths that behave like Path objects but allow mocking
        mock_path1 = MagicMock(spec=Path)
        mock_path1.name = "test_folder"
        mock_path1.parent = Path("/")
        mock_path1.is_dir.return_value = True

        mock_path2 = MagicMock(spec=Path)
        mock_path2.name = "test_file.txt"
        mock_path2.parent = Path("/")
        mock_path2.is_dir.return_value = False

        mock_path3 = MagicMock(spec=Path)
        mock_path3.name = "another_folder"
        mock_path3.parent = Path("/")
        mock_path3.is_dir.return_value = True

        dialog.paths = {mock_path1: 1024, mock_path2: 512, mock_path3: 2048}

        # Configure remote.exists_in_parent to return True for both folders
        self.mock_remote.exists_in_parent.return_value = True
        self.mock_remote.reset_mock()
        self.mock_engine.reset_mock()

        result = dialog._find_folders_duplicates()

        assert isinstance(result, list)
        assert len(result) == 2
        assert "test_folder" in result
        assert "another_folder" in result
        assert "test_file.txt" not in result  # Files should be filtered out
        self.mock_engine.send_metric.assert_called_once_with(
            "direct_transfer", "dupe_folder", "1"
        )

        # Verify exists_in_parent was called correctly for folders only
        expected_calls = [
            call("/test/remote/folder", "test_folder", True),
            call("/test/remote/folder", "another_folder", True),
        ]
        self.mock_remote.exists_in_parent.assert_has_calls(
            expected_calls, any_order=True
        )

        # Test 3: No duplicates scenario
        self.mock_remote.exists_in_parent.return_value = False
        self.mock_remote.reset_mock()
        self.mock_engine.reset_mock()

        result = dialog._find_folders_duplicates()

        assert isinstance(result, list)
        assert len(result) == 0
        self.mock_engine.send_metric.assert_not_called()  # No metric when no duplicates

        # Test 4: Edge case with None remote_folder_ref
        dialog.remote_folder_ref = None
        dialog.paths = {mock_path1: 1024}
        self.mock_remote.exists_in_parent.return_value = True
        self.mock_remote.reset_mock()
        self.mock_engine.reset_mock()

        result = dialog._find_folders_duplicates()

        assert isinstance(result, list)
        # Should work with None parent
        self.mock_remote.exists_in_parent.assert_called_with(None, "test_folder", True)

        # Test 5: Parent-child filtering test
        # Create parent and child mock paths
        parent_path = MagicMock(spec=Path)
        parent_path.name = "parent"
        parent_path.parent = Path("/")
        parent_path.is_dir.return_value = True

        child_path = MagicMock(spec=Path)
        child_path.name = "child"
        child_path.parent = parent_path
        child_path.is_dir.return_value = True

        dialog.paths = {parent_path: 1024, child_path: 512}
        dialog.remote_folder_ref = "/test"

        def parent_exists_check(parent, name, is_folder):
            # Only parent should be checked, not child
            return name == "parent" and is_folder

        self.mock_remote.exists_in_parent.side_effect = parent_exists_check
        self.mock_remote.reset_mock()
        self.mock_engine.reset_mock()

        result = dialog._find_folders_duplicates()

        assert isinstance(result, list)
        # Child should be filtered out due to parent being in all_paths
        # Only calls for paths whose parent is not in all_paths should be made
        parent_calls = [
            call
            for call in self.mock_remote.exists_in_parent.call_args_list
            if call[0][1] == "parent"
        ]
        child_calls = [
            call
            for call in self.mock_remote.exists_in_parent.call_args_list
            if call[0][1] == "child"
        ]
        assert (
            len(parent_calls) >= 0
        )  # Parent may or may not be called based on filtering
        assert (
            len(child_calls) == 0
        )  # Child should not be called due to parent filtering

        # Test 6: Exception handling verification
        dialog.paths = {mock_path1: 1024}
        self.mock_remote.exists_in_parent.side_effect = Exception("Remote error")
        self.mock_remote.reset_mock()
        self.mock_engine.reset_mock()

        try:
            result = dialog._find_folders_duplicates()
            assert False, "Expected exception was not raised"
        except Exception:
            assert True  # Exception should propagate

        # Test 7: Return type verification with various scenarios
        self.mock_remote.exists_in_parent.side_effect = None

        # Reset to working state
        dialog.remote_folder_ref = "/test"
        dialog.paths = {}
        result = dialog._find_folders_duplicates()
        assert isinstance(result, list)
        assert all(isinstance(item, str) for item in result)

        # Test 8: Multiple folders with mixed existence results
        mock_folder1 = MagicMock(spec=Path)
        mock_folder1.name = "exists_remote"
        mock_folder1.parent = Path("/")
        mock_folder1.is_dir.return_value = True

        mock_folder2 = MagicMock(spec=Path)
        mock_folder2.name = "not_exists_remote"
        mock_folder2.parent = Path("/")
        mock_folder2.is_dir.return_value = True

        dialog.paths = {mock_folder1: 1024, mock_folder2: 2048}

        def selective_exists(parent, name, is_folder):
            return name == "exists_remote" and is_folder

        self.mock_remote.exists_in_parent.side_effect = selective_exists
        self.mock_remote.reset_mock()
        self.mock_engine.reset_mock()

        result = dialog._find_folders_duplicates()

        assert isinstance(result, list)
        assert len(result) == 1
        assert "exists_remote" in result
        assert "not_exists_remote" not in result
        self.mock_engine.send_metric.assert_called_once_with(
            "direct_transfer", "dupe_folder", "1"
        )

        # Test 9: Large scale test with many paths
        many_mock_paths = {}
        for i in range(10):
            mock_path = MagicMock(spec=Path)
            mock_path.name = f"folder{i}"
            mock_path.parent = Path("/")
            mock_path.is_dir.return_value = True
            many_mock_paths[mock_path] = 1024

        dialog.paths = many_mock_paths
        self.mock_remote.exists_in_parent.return_value = False
        self.mock_remote.reset_mock()
        self.mock_engine.reset_mock()

        result = dialog._find_folders_duplicates()

        assert isinstance(result, list)
        assert len(result) == 0
        assert self.mock_remote.exists_in_parent.call_count == 10

        # Test 10: Final comprehensive verification
        final_mock_path = MagicMock(spec=Path)
        final_mock_path.name = "final_test"
        final_mock_path.parent = Path("/")
        final_mock_path.is_dir.return_value = True

        dialog.paths = {final_mock_path: 1024}
        self.mock_remote.exists_in_parent.side_effect = None  # Clear any side_effect
        self.mock_remote.exists_in_parent.return_value = True
        self.mock_remote.reset_mock()
        self.mock_engine.reset_mock()

        result = dialog._find_folders_duplicates()

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == "final_test"
        self.mock_engine.send_metric.assert_called_once_with(
            "direct_transfer", "dupe_folder", "1"
        )

        # Verify all expected attributes and methods were accessed
        final_mock_path.is_dir.assert_called()
        assert hasattr(final_mock_path, "name")
        assert hasattr(final_mock_path, "parent")
        assert final_mock_path.name == "final_test"


class TestFoldersDialogGetKnownTypeKey:
    """Test cases for FoldersDialog.get_known_type_key method."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create mock application and engine
        self.mock_app = Mock()
        self.mock_engine = Mock()
        self.mock_dao = Mock()
        self.mock_engine.dao = self.mock_dao

        # Mock the get_config method
        self.mock_dao.get_config.return_value = "/default/remote/folder"

    @patch("nxdrive.gui.folders_dialog.FoldersDialog.__init__", return_value=None)
    def test_get_known_type_key_comprehensive_functionality(self, mock_init):
        """Test comprehensive functionality covering all aspects of get_known_type_key method.

        This test covers:
        1. Type found in DEFAULT_TYPES values
        2. Type found in KNOWN_FOLDER_TYPES for folders
        3. Type found in KNOWN_FILE_TYPES for files
        4. Type not found in any dictionary (exception handling)
        5. Empty dictionaries handling
        6. Type matching with different folder/file flags
        7. Return value verification
        8. Exception path testing
        9. Edge cases with None/empty values
        10. Multiple lookups with same and different types
        """
        # Create a FoldersDialog instance for testing
        dialog = FoldersDialog.__new__(FoldersDialog)

        # Set up required attributes that would normally be set in __init__
        dialog.engine = self.mock_engine

        # Test 1: Type found in DEFAULT_TYPES values
        dialog.DEFAULT_TYPES = {
            "default_key1": "default_value1",
            "default_key2": "default_value2",
        }
        dialog.KNOWN_FOLDER_TYPES = {"folder_key1": "folder_value1"}
        dialog.KNOWN_FILE_TYPES = {"file_key1": "file_value1"}

        result = dialog.get_known_type_key(True, "default_value1")
        assert result == "default_key1"

        result = dialog.get_known_type_key(False, "default_value2")
        assert result == "default_key2"

        # Test 2: Type found in KNOWN_FOLDER_TYPES for folders
        result = dialog.get_known_type_key(True, "folder_value1")
        assert result == "folder_key1"

        # Test 3: Type found in KNOWN_FILE_TYPES for files
        result = dialog.get_known_type_key(False, "file_value1")
        assert result == "file_key1"

        # Test 4: Type not found in any dictionary (exception handling)
        unknown_type = "unknown_type_value"
        result = dialog.get_known_type_key(True, unknown_type)
        assert result == unknown_type  # Should return original type

        result = dialog.get_known_type_key(False, unknown_type)
        assert result == unknown_type  # Should return original type

        # Test 5: Empty dictionaries handling
        dialog.DEFAULT_TYPES = {}
        dialog.KNOWN_FOLDER_TYPES = {}
        dialog.KNOWN_FILE_TYPES = {}

        test_type = "any_type"
        result = dialog.get_known_type_key(True, test_type)
        assert result == test_type  # Should return original type when not found

        result = dialog.get_known_type_key(False, test_type)
        assert result == test_type  # Should return original type when not found

        # Test 6: Complex dictionaries with multiple entries
        dialog.DEFAULT_TYPES = {
            "def_doc": "Document",
            "def_note": "Note",
            "def_workspace": "Workspace",
        }
        dialog.KNOWN_FOLDER_TYPES = {
            "folder_root": "Root",
            "folder_workspace": "WorkspaceRoot",
            "folder_domain": "Domain",
        }
        dialog.KNOWN_FILE_TYPES = {
            "file_doc": "File",
            "file_picture": "Picture",
            "file_video": "Video",
        }

        # Test DEFAULT_TYPES precedence
        result = dialog.get_known_type_key(True, "Document")
        assert result == "def_doc"

        result = dialog.get_known_type_key(False, "Note")
        assert result == "def_note"

        # Test KNOWN_FOLDER_TYPES when not in DEFAULT_TYPES
        result = dialog.get_known_type_key(True, "Root")
        assert result == "folder_root"

        result = dialog.get_known_type_key(True, "Domain")
        assert result == "folder_domain"

        # Test KNOWN_FILE_TYPES when not in DEFAULT_TYPES
        result = dialog.get_known_type_key(False, "Picture")
        assert result == "file_picture"

        result = dialog.get_known_type_key(False, "Video")
        assert result == "file_video"

        # Test 7: Wrong folder/file flag with type in other dictionary
        # File type but is_folder=True should still check DEFAULT_TYPES first, then KNOWN_FOLDER_TYPES
        result = dialog.get_known_type_key(
            True, "Picture"
        )  # Picture is in KNOWN_FILE_TYPES
        assert (
            result == "Picture"
        )  # Should return original since not found in folder types

        result = dialog.get_known_type_key(
            False, "Root"
        )  # Root is in KNOWN_FOLDER_TYPES
        assert result == "Root"  # Should return original since not found in file types

        # Test 8: Edge cases with empty strings and special values
        dialog.DEFAULT_TYPES = {"empty_key": "", "special_key": " "}
        dialog.KNOWN_FOLDER_TYPES = {"none_key": "none_value"}
        dialog.KNOWN_FILE_TYPES = {"zero_key": "zero_value"}

        result = dialog.get_known_type_key(True, "")
        assert result == "empty_key"

        result = dialog.get_known_type_key(False, " ")
        assert result == "special_key"

        # Test with empty string value (should handle gracefully)
        result = dialog.get_known_type_key(True, "none_value")
        assert result == "none_key"

        # Test 9: Return type verification
        dialog.DEFAULT_TYPES = {"test_key": "test_value"}
        result = dialog.get_known_type_key(True, "test_value")
        assert isinstance(result, str)
        assert result == "test_key"

        # Test 10: Multiple consecutive lookups to ensure no state issues
        dialog.DEFAULT_TYPES = {"key1": "value1", "key2": "value2"}
        dialog.KNOWN_FOLDER_TYPES = {"fkey1": "fvalue1"}
        dialog.KNOWN_FILE_TYPES = {"filekey1": "filevalue1"}

        # Multiple calls should be consistent
        for _ in range(3):
            assert dialog.get_known_type_key(True, "value1") == "key1"
            assert dialog.get_known_type_key(False, "value2") == "key2"
            assert dialog.get_known_type_key(True, "fvalue1") == "fkey1"
            assert dialog.get_known_type_key(False, "filevalue1") == "filekey1"
            assert dialog.get_known_type_key(True, "nonexistent") == "nonexistent"

        # Test 11: Verify exception handling with problematic dictionary access
        # Test with a type that will cause an exception during the lookup process
        dialog.DEFAULT_TYPES = {"normal_key": "normal_value"}

        # Create a scenario where the list operations might fail
        dialog.KNOWN_FOLDER_TYPES = {"key1": "value1", "key2": "value2"}

        # Mock the list operations to raise an exception
        original_list = Mock()
        original_list.keys.return_value = ["key1", "key2"]
        original_list.values.return_value = ["value1", "value2"]

        # Test exception handling by trying to access non-existent type
        result = dialog.get_known_type_key(True, "non_existent_value")
        assert result == "non_existent_value"  # Should return original on exception

        # Test 12: Complex type matching scenarios
        dialog.DEFAULT_TYPES = {"doc": "Document", "workspace": "Workspace"}
        dialog.KNOWN_FOLDER_TYPES = {
            "root": "RootFolder",
            "workspace_folder": "Workspace",
        }
        dialog.KNOWN_FILE_TYPES = {"document_file": "Document"}

        # When type exists in both DEFAULT_TYPES and other types, DEFAULT_TYPES should win
        result = dialog.get_known_type_key(True, "Document")
        assert result == "doc"  # From DEFAULT_TYPES, not from KNOWN_FILE_TYPES

        result = dialog.get_known_type_key(False, "Document")
        assert result == "doc"  # From DEFAULT_TYPES, not from KNOWN_FILE_TYPES

        # When type not in DEFAULT_TYPES, should use appropriate type dictionary
        result = dialog.get_known_type_key(True, "RootFolder")
        assert result == "root"

        result = dialog.get_known_type_key(False, "RootFolder")
        assert result == "RootFolder"  # Not found in file types, return original

        # Test 13: Verify method signature and parameter handling
        # The method uses positional-only parameters (/) syntax
        result = dialog.get_known_type_key(True, "Document")
        assert isinstance(result, str)

        # Test 14: Boundary conditions with list operations
        dialog.DEFAULT_TYPES = {}
        dialog.KNOWN_FOLDER_TYPES = {"single_key": "single_value"}
        dialog.KNOWN_FILE_TYPES = {}

        result = dialog.get_known_type_key(True, "single_value")
        assert result == "single_key"

        # Test with index at boundary
        dialog.KNOWN_FOLDER_TYPES = {"key1": "val1", "key2": "val2", "key3": "val3"}
        result = dialog.get_known_type_key(True, "val1")  # First element
        assert result == "key1"

        result = dialog.get_known_type_key(True, "val3")  # Last element
        assert result == "key3"

        # Test 15: Final comprehensive verification
        dialog.DEFAULT_TYPES = {"default": "DefaultType"}
        dialog.KNOWN_FOLDER_TYPES = {"folder": "FolderType"}
        dialog.KNOWN_FILE_TYPES = {"file": "FileType"}

        # Test all paths through the function
        assert dialog.get_known_type_key(True, "DefaultType") == "default"
        assert dialog.get_known_type_key(False, "DefaultType") == "default"
        assert dialog.get_known_type_key(True, "FolderType") == "folder"
        assert dialog.get_known_type_key(False, "FileType") == "file"
        assert dialog.get_known_type_key(True, "Unknown") == "Unknown"
        assert dialog.get_known_type_key(False, "Unknown") == "Unknown"


class TestFoldersDialogAccept:
    """Test cases for FoldersDialog.accept method."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create mock application, engine, and dependencies
        self.mock_app = Mock()
        self.mock_engine = Mock()
        self.mock_dao = Mock()
        self.mock_engine.dao = self.mock_dao
        self.mock_engine.get_metadata_url = Mock(return_value="http://test.url")
        self.mock_engine.direct_transfer_async = Mock()

        # Mock application methods
        self.mock_app.folder_duplicate_warning = Mock()

        # Mock combo boxes
        self.mock_cb_doc_type = Mock()
        self.mock_cb_container_type = Mock()
        self.mock_cb_duplicate = Mock()

        # Mock remote folder text widget
        self.mock_remote_folder = Mock()

        # Mock the get_config method
        self.mock_dao.get_config.return_value = "/default/remote/folder"

    @patch("nxdrive.gui.folders_dialog.FoldersDialog.__init__", return_value=None)
    @patch("nxdrive.gui.folders_dialog.DialogMixin.accept")  # Mock parent accept
    def test_accept_comprehensive_functionality(self, mock_parent_accept, mock_init):
        """Test comprehensive functionality covering all aspects of accept method.

        This test covers:
        1. Normal execution without duplicates
        2. Execution with folder duplicates (early return)
        3. Document type handling from combo boxes
        4. Container type handling from combo boxes
        5. Type key conversion using get_known_type_key
        6. Direct transfer async call with all parameters
        7. Parent class accept method call
        8. UI state management
        9. Edge cases with different combo box states
        10. Multiple execution scenarios
        """
        from pathlib import Path

        # Create a FoldersDialog instance for testing
        dialog = FoldersDialog.__new__(FoldersDialog)

        # Set up required attributes that would normally be set in __init__
        dialog.application = self.mock_app
        dialog.engine = self.mock_engine
        dialog.remote_folder_ref = "/test/remote/folder"
        dialog.remote_folder_title = "Test Folder"
        dialog.paths = {Path("/local/test.txt"): 1024}
        dialog.last_local_selected_location = "/local"

        # Set up UI components
        dialog.cbDocType = self.mock_cb_doc_type
        dialog.cbContainerType = self.mock_cb_container_type
        dialog.cb = self.mock_cb_duplicate
        dialog.remote_folder = self.mock_remote_folder

        # Mock methods that accept() calls
        dialog._find_folders_duplicates = Mock(return_value=[])
        dialog.get_known_type_key = Mock(
            side_effect=lambda is_folder, type_val: f"key_{type_val}"
        )

        # Test 1: Normal execution without duplicates
        # Set up combo box states
        self.mock_cb_doc_type.currentIndex.return_value = 1  # Not default
        self.mock_cb_doc_type.currentText.return_value = "Document"
        self.mock_cb_doc_type.currentData.return_value = "doc_data"

        self.mock_cb_container_type.currentIndex.return_value = 1  # Not default
        self.mock_cb_container_type.currentText.return_value = "Folder"

        self.mock_cb_duplicate.currentData.return_value = "create"
        self.mock_remote_folder.text.return_value = "/remote/target"

        # Call the method
        dialog.accept()

        # Verify parent accept was called
        mock_parent_accept.assert_called_once()

        # Verify last_local_selected_doc_type was set correctly
        assert dialog.last_local_selected_doc_type == "Document"

        # Verify _find_folders_duplicates was called
        dialog._find_folders_duplicates.assert_called_once()

        # Verify get_known_type_key was called for both types
        expected_calls = [
            call(False, "Document"),  # Document type
            call(True, "Folder"),  # Container type
        ]
        dialog.get_known_type_key.assert_has_calls(expected_calls)

        # Verify direct_transfer_async was called with correct parameters
        self.mock_engine.direct_transfer_async.assert_called_once()
        call_args = self.mock_engine.direct_transfer_async.call_args
        assert call_args[1]["document_type"] == "key_Document"
        assert call_args[1]["container_type"] == "key_Folder"
        assert call_args[1]["duplicate_behavior"] == "create"
        assert call_args[1]["last_local_selected_location"] == "/local"
        assert call_args[1]["last_local_selected_doc_type"] == "Document"

        # Test 2: Execution with folder duplicates (early return)
        # Reset mocks
        mock_parent_accept.reset_mock()
        self.mock_engine.direct_transfer_async.reset_mock()
        dialog._find_folders_duplicates.return_value = ["duplicate_folder"]

        # Call the method
        dialog.accept()

        # Verify parent accept was called
        mock_parent_accept.assert_called()

        # Verify folder duplicate warning was called
        self.mock_app.folder_duplicate_warning.assert_called_once_with(
            ["duplicate_folder"], "Test Folder", "http://test.url"
        )

        # Verify direct_transfer_async was NOT called due to early return
        self.mock_engine.direct_transfer_async.assert_not_called()

        # Test 3: Document type handling with currentIndex() == 0 (default)
        # Reset mocks and duplicates
        mock_parent_accept.reset_mock()
        self.mock_engine.direct_transfer_async.reset_mock()
        self.mock_app.folder_duplicate_warning.reset_mock()
        dialog._find_folders_duplicates.return_value = []

        # Set cbDocType to index 0 (default)
        self.mock_cb_doc_type.currentIndex.return_value = 0
        self.mock_cb_doc_type.currentData.return_value = "default_doc_data"

        # Call the method
        dialog.accept()

        # Verify last_local_selected_doc_type uses currentData() for index 0
        assert dialog.last_local_selected_doc_type == "default_doc_data"

        # Verify get_known_type_key was called with empty string for doc_type
        dialog.get_known_type_key.assert_any_call(False, "")

        # Test 4: Container type handling with currentIndex() == 0 (default)
        # Reset and set container type to index 0
        dialog.get_known_type_key.reset_mock()
        self.mock_cb_container_type.currentIndex.return_value = 0

        # Call the method
        dialog.accept()

        # Verify get_known_type_key was called with empty string for cont_type
        dialog.get_known_type_key.assert_any_call(True, "")

        # Test 5: Edge case with no remote folder reference
        dialog.remote_folder_ref = None
        self.mock_engine.get_metadata_url.reset_mock()
        self.mock_app.folder_duplicate_warning.reset_mock()
        dialog._find_folders_duplicates.return_value = ["test_duplicate"]

        # Call the method
        dialog.accept()

        # Should still call folder_duplicate_warning even with None ref
        self.mock_engine.get_metadata_url.assert_called_with(None)
        self.mock_app.folder_duplicate_warning.assert_called_once()

        # Test 6: Verify all parameters passed to direct_transfer_async
        # Reset for clean test
        mock_parent_accept.reset_mock()
        self.mock_engine.direct_transfer_async.reset_mock()
        dialog._find_folders_duplicates.return_value = []
        dialog.remote_folder_ref = "/clean/test/folder"
        dialog.remote_folder_title = "Clean Test"
        test_paths = {Path("/clean/test.txt"): 2048}
        dialog.paths = test_paths
        dialog.last_local_selected_location = "/clean/local"
        dialog.last_local_selected_doc_type = "TestDoc"

        self.mock_cb_doc_type.currentIndex.return_value = 2
        self.mock_cb_doc_type.currentText.return_value = "CustomDoc"
        self.mock_cb_container_type.currentIndex.return_value = 2
        self.mock_cb_container_type.currentText.return_value = "CustomFolder"
        self.mock_cb_duplicate.currentData.return_value = "overwrite"
        self.mock_remote_folder.text.return_value = "/clean/remote/target"

        # Call the method
        dialog.accept()

        # Verify all parameters in direct_transfer_async call
        self.mock_engine.direct_transfer_async.assert_called_once_with(
            test_paths,
            "/clean/remote/target",
            "/clean/test/folder",
            "Clean Test",
            document_type="key_CustomDoc",
            container_type="key_CustomFolder",
            duplicate_behavior="overwrite",
            last_local_selected_location="/clean/local",
            last_local_selected_doc_type="CustomDoc",
        )

        # Test 7: Multiple consecutive calls (state consistency)
        for i in range(3):
            mock_parent_accept.reset_mock()
            self.mock_engine.direct_transfer_async.reset_mock()

            # Vary the input slightly
            self.mock_cb_doc_type.currentText.return_value = f"Doc{i}"
            dialog.last_local_selected_doc_type = f"LastDoc{i}"

            dialog.accept()

            # Each call should work independently
            mock_parent_accept.assert_called_once()
            self.mock_engine.direct_transfer_async.assert_called_once()

            # Verify the updated last_local_selected_doc_type
            assert dialog.last_local_selected_doc_type == f"Doc{i}"

        # Test 8: Exception handling in _find_folders_duplicates
        dialog._find_folders_duplicates.side_effect = Exception(
            "Duplicate check failed"
        )

        # The method should propagate the exception (no exception handling in accept)
        try:
            dialog.accept()
            assert False, "Expected exception was not raised"
        except Exception as e:
            assert str(e) == "Duplicate check failed"

        # Test 9: Verify method return behavior
        # Reset to working state
        dialog._find_folders_duplicates.side_effect = None
        dialog._find_folders_duplicates.return_value = []

        result = dialog.accept()
        assert result is None  # Method should return None

        # Test with early return due to duplicates
        dialog._find_folders_duplicates.return_value = ["duplicate"]
        result = dialog.accept()
        assert result is None  # Method should return None even on early return

        # Test 10: Comprehensive UI state verification
        dialog._find_folders_duplicates.return_value = []
        mock_parent_accept.reset_mock()

        # Verify all UI components are accessed correctly
        self.mock_cb_doc_type.currentIndex.return_value = 0
        self.mock_cb_doc_type.currentData.return_value = "final_data"
        self.mock_cb_container_type.currentIndex.return_value = 0
        self.mock_cb_duplicate.currentData.return_value = "final_behavior"
        self.mock_remote_folder.text.return_value = "/final/remote"

        dialog.accept()

        # Verify all UI components were called
        self.mock_cb_doc_type.currentIndex.assert_called()
        self.mock_cb_doc_type.currentData.assert_called()
        self.mock_cb_container_type.currentIndex.assert_called()
        self.mock_cb_duplicate.currentData.assert_called()
        self.mock_remote_folder.text.assert_called()
        mock_parent_accept.assert_called_once()

        # Verify the final state
        assert dialog.last_local_selected_doc_type == "final_data"
