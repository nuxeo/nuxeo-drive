/*
 * (C) Copyright 2012 Nuxeo SA (http://nuxeo.com/) and contributors.
 *
 * All rights reserved. This program and the accompanying materials
 * are made available under the terms of the GNU Lesser General Public License
 * (LGPL) version 2.1 which accompanies this distribution, and is available at
 * http://www.gnu.org/licenses/lgpl.html
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * Lesser General Public License for more details.
 *
 * Contributors:
 *     Olivier Grisel <ogrisel@nuxeo.com>
 *     Antoine Taillefer <ataillefer@nuxeo.com>
 */
package org.nuxeo.drive.service;

import java.util.Calendar;
import java.util.Set;

import org.nuxeo.drive.service.impl.DocumentChangeSummary;
import org.nuxeo.ecm.core.api.ClientException;
import org.nuxeo.ecm.core.api.CoreSession;
import org.nuxeo.ecm.core.api.DocumentModel;
import org.nuxeo.ecm.core.api.IdRef;
import org.nuxeo.ecm.core.security.SecurityException;

/**
 * Manage list of NuxeoDrive synchronization roots and devices for a given nuxeo
 * user.
 */
public interface NuxeoDriveManager {

    /**
     * @param userName the id of the Nuxeo Drive user
     * @param newRootContainer the folderish document to be used as
     *            synchronization root: must be bound to an active session
     * @throws ClientException
     * @throws SecurityException if the user does not have write permissions to
     *             the container.
     */
    public void registerSynchronizationRoot(String userName,
            DocumentModel newRootContainer, CoreSession session)
            throws ClientException, SecurityException;

    /**
     * @param userName the id of the Nuxeo Drive user
     * @param rootContainer the folderish document that should no longer be used
     *            as a synchronization root
     */
    public void unregisterSynchronizationRoot(String userName,
            DocumentModel rootContainer, CoreSession session)
            throws ClientException;

    /**
     * Fetch the list of synchronization root ids for a given user. This list is
     * assumed to be short enough (in the order of 100 folder max) so that no
     * paging API is required.
     *
     * @param userName the id of the Nuxeo Drive user
     * @param session active CoreSession instance to the repository hosting the
     *            roots.
     * @return the ordered set of non deleted synchronization root references
     *         for that user
     * @see #getSynchronizationRootPaths(String, CoreSession)
     */
    public Set<IdRef> getSynchronizationRootReferences(String userName,
            CoreSession session) throws ClientException;

    /**
     * Fetch the list of synchronization root paths for a given user. This list
     * is assumed to be short enough (in the order of 100 folder max) so that no
     * paging API is required.
     *
     * @param userName the id of the Nuxeo Drive user
     * @param session active CoreSession instance to the repository hosting the
     *            roots.
     * @return the ordered set of non deleted synchronization root paths for
     *         that user
     * @see #getSynchronizationRootReferences(String, CoreSession)
     */
    public Set<String> getSynchronizationRootPaths(String userName,
            CoreSession session) throws ClientException;

    /**
     * Method to be called by a CoreEvent listener monitoring documents
     * deletions to cleanup references to recently deleted documents and
     * invalidate the caches.
     */
    public void handleFolderDeletion(IdRef ref) throws ClientException;

    /**
     * Gets a summary of document changes on the given user's synchronization
     * roots since the user's device last successful synchronization date.
     * <p>
     * The summary includes:
     * <ul>
     * <li>A list of document changes</li>
     * <li>The document models that have changed</li>
     * <li>A status code</li>
     * </ul>
     *
     * @param userName the id of the Nuxeo Drive user
     * @param session active CoreSession instance to the repository hosting the
     *            user's synchronization roots
     * @param lastSuccessfulSync the last successful synchronization date of the
     *            user's device
     * @return the summary of document changes
     */
    public DocumentChangeSummary getDocumentChangeSummary(String userName,
            CoreSession session, Calendar lastSuccessfulSync)
            throws ClientException;

}
