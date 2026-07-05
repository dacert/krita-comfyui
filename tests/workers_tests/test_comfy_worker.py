import asyncio
from time import sleep
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PyQt5.QtCore import QCoreApplication, QObject, QThreadPool

from krita_comfyui.config import Config, WorkflowConfig, WorkflowInput

# Import the module under test (adjust the import path if necessary)
from krita_comfyui.workers.comfy_worker import ComfyWorker


class SignalCatcher(QObject):
    """Collects emitted signals into lists."""

    def __init__(self):
        super().__init__()
        self.finished = []
        self.error = []
        self.progress = []

    def connect(self, worker: ComfyWorker):
        worker.signals.finished.connect(self._on_finished)
        worker.signals.error.connect(self._on_error)
        worker.signals.progress.connect(self._on_progress)

    def _on_finished(self, data):
        self.finished.append(data)

    def _on_error(self, msg):
        self.error.append(msg)

    def _on_progress(self, val):
        self.progress.append(val)


@pytest.fixture
def qapp():
    """Ensure a QCoreApplication instance exists for signal/slot handling."""
    return QCoreApplication([])


# ----------------------------------------------------------------------
#  NEW: minimal Config fixture
# ----------------------------------------------------------------------
@pytest.fixture
def mock_cfg() -> Config:
    """
    Create a minimal `Config` instance with one workflow.
    The workflow contains three inputs that the worker will use.
    """
    wf = WorkflowConfig(
        workflow_name="test_wf",
        inputs={
            "prompt": WorkflowInput(node_id="node_prompt", property="text"),
            "seed": WorkflowInput(node_id="node_seed", property="value"),
            "image_loader": WorkflowInput(node_id="node_image", property="path"),
        },
    )
    # Provide required fields for Config
    return Config(
        logger=False,
        comfyui_url="http://localhost:8000",
        workflows=[wf],
    )


@pytest.fixture
def http_client_mock():
    """Mock del cliente HTTP usado por ComfyWorker."""
    mock = MagicMock()
    # Configuración estándar (puedes cambiarla en un solo lugar)
    mock.get_workflow_api.return_value = {"nodes": {}, "edges": []}
    mock.upload_file.return_value = None
    mock.queue_prompt.return_value = {"prompt_id": "dummy"}
    return mock


@pytest.fixture
def prompt_builder_mock():
    """Mock de PromptBuilder que siempre devuelve la misma carga."""
    payload = {"nodes": {"node_output": {}}, "edges": []}
    builder = MagicMock()
    builder.build.return_value = payload
    return builder


@pytest.fixture
def output_node_patch(monkeypatch):
    """
    Parches `find_output_node` para devolver un nodo válido.
    Se puede parametrizar si se necesita el caso de “sin salida”.
    """

    def _patch(return_value=("node_output", None)):
        monkeypatch.setattr(
            "krita_comfyui.workers.comfy_worker.find_output_node",
            lambda *_, **__: return_value,
        )

    return _patch


@pytest.fixture
def mock_client_factory():
    """
    Factory that creates a mocked ComfyClient with configurable behaviour.
    """

    def _factory(*, run_images=None, raise_on_run=False, progress_values=None, uploaded_name=None):
        client_mock = MagicMock()
        client_mock.__aenter__ = AsyncMock(return_value=client_mock)
        client_mock.__aexit__ = AsyncMock()

        # Mock upload_images to return the uploaded filename
        client_mock.upload_images = MagicMock(return_value=uploaded_name)

        if raise_on_run:
            client_mock.run_workflow.side_effect = Exception("run error")
        else:

            async def _run(*_, **kwargs):
                # Simulate progress updates
                progress_cb = kwargs.get("progress_callback")

                # Simulate sending progress updates
                if progress_values and progress_cb:
                    for p in progress_values:
                        await asyncio.sleep(0)  # yield control to event loop
                        progress_cb(p)

                return run_images or {}

            client_mock.run_workflow = AsyncMock(side_effect=_run)

        return client_mock

    return _factory


def _run_comfy_worker_and_wait(worker: ComfyWorker, qapp):
    """
    Helper that starts the worker in the global QThreadPool and blocks
    until it emits either `finished` or `error`.
    Returns the emitted data on success, otherwise raises RuntimeError.
    """
    pool = QThreadPool()
    if pool is None:
        pytest.fail("QThreadPool is None.")
        return

    catcher = SignalCatcher()
    catcher.connect(worker)
    pool.start(worker)

    timeout_ms = 2000
    while not (len(catcher.finished) or len(catcher.error)):
        qapp.processEvents()
        if timeout_ms <= 0:
            break
        sleep(0.01)
        timeout_ms -= 10

    pool.clear()
    if not (len(catcher.finished) or len(catcher.error)):
        pytest.fail("ComfyWorker did not emit finished or error signal within timeout.")

    return catcher


# ----------------------------------------------------------------------
#  Test cases
# ----------------------------------------------------------------------
def test_worker_success_no_image(
    qapp,
    mock_cfg,
    mock_client_factory,
    http_client_mock,
    prompt_builder_mock,
    output_node_patch,
):
    """
    Normal execution path without an image prompt.
    The worker should emit progress updates and a finished signal with images.
    """

    output_node_patch()
    expected_images = {"node1": [b"imagebytes"]}
    http_client_mock.get_workflow_api.return_value = {
        "nodes": {"node_prompt": {}, "node_seed": {}},
        "edges": [],
    }

    prompt_builder_mock.build.return_value = {"nodes": {"node_output": {}}, "edges": []}

    with (
        patch("krita_comfyui.workers.comfy_worker.ComfyHttpClient", return_value=http_client_mock),
        patch("krita_comfyui.workers.comfy_worker.PromptBuilder", new_callable=prompt_builder_mock),
    ):
        mock_client = mock_client_factory(
            run_images=expected_images,
            progress_values=[10.0, 50.0, 100.0],
        )

        with patch("krita_comfyui.workers.comfy_worker.ComfyClient", return_value=mock_client):
            worker = ComfyWorker(
                logger=MagicMock(),
                server_url="http://localhost",
                workflow_name="test_wf",
                prompt_text="some text",
                cfg=mock_cfg,
                seed=1234,
                image_prompt=None,
            )

            # Act
            catcher = _run_comfy_worker_and_wait(worker, qapp)

    # Assert
    assert len(catcher.error) == 0, f"Unexpected error signals: {catcher.error}"
    assert catcher.progress == [10.0, 50.0, 100.0]
    assert catcher.finished[0] == expected_images


def test_worker_success_with_image(
    qapp, mock_cfg, mock_client_factory, http_client_mock, prompt_builder_mock, output_node_patch
):
    """
    Execution path when an image prompt is supplied.
    The worker should upload images first, then pass the uploaded name to PromptBuilder.
    """

    output_node_patch()
    expected_images = {"node2": [b"imgbytes"]}

    http_client_mock.get_workflow_api.return_value = {
        "nodes": {"node_prompt": {}, "node_seed": {}, "node_image": {}},
        "edges": [],
    }
    prompt_builder_mock.build.return_value = {"nodes": {"node_output": {}}, "edges": []}

    image_prompt = MagicMock()
    image_prompt.has_image_data.return_value = True
    image_prompt.image_bytes = b"fakebytes"
    image_prompt.width = 100
    image_prompt.height = 100
    image_prompt.sel_bytes = b"sel"

    # The actual uploaded filename returned by the server
    uploaded_filename = "clipspace/painted_mask.png [input]"

    mock_client = mock_client_factory(
        run_images=expected_images,
        progress_values=[25.0, 75.0],
        uploaded_name=uploaded_filename,
    )

    with (
        patch("krita_comfyui.workers.comfy_worker.ComfyHttpClient", return_value=http_client_mock),
        patch("krita_comfyui.workers.comfy_worker.PromptBuilder", return_value=prompt_builder_mock),
        patch("krita_comfyui.workers.comfy_worker.ComfyClient", return_value=mock_client),
    ):
        worker = ComfyWorker(
            logger=MagicMock(),
            server_url="http://localhost",
            workflow_name="test_wf",
            prompt_text="text",
            cfg=mock_cfg,
            seed=None,
            image_prompt=image_prompt,
        )

        # Act
        catcher = _run_comfy_worker_and_wait(worker, qapp)

    # Assert
    assert len(catcher.error) == 0, f"Unexpected error signals: {catcher.error}"
    assert catcher.progress == [25.0, 75.0]
    assert catcher.finished[0] == expected_images

    # Verify upload_images was called with the image_prompt
    mock_client.upload_images.assert_called_once_with(image_prompt)

    # Verify PromptBuilder.build was called with the uploaded filename
    prompt_builder_mock.build.assert_called_once()
    _args, _kwargs = prompt_builder_mock.build.call_args
    # build(wf_api, workflow_name, base_prompt, image_input_name, seed)
    # image_input_name is the 4th positional argument (index 3)
    assert _args[3] == uploaded_filename

    # Verify run_workflow no longer receives image_prompt (upload is done before)
    mock_client.run_workflow.assert_awaited_once()
    _rf_args, rf_kwargs = mock_client.run_workflow.call_args
    assert "image_prompt" not in rf_kwargs


def test_worker_missing_output_node(qapp, mock_cfg, http_client_mock, prompt_builder_mock):
    """
    When find_output_node returns None the worker should emit an error signal.
    """
    http_client_mock.get_workflow_api.return_value = {"nodes": {}, "edges": []}
    prompt_builder_mock.build.return_value = {"nodes": {"node_output": {}}, "edges": []}

    with (
        patch("krita_comfyui.workers.comfy_worker.ComfyHttpClient", return_value=http_client_mock),
        patch("krita_comfyui.workers.comfy_worker.PromptBuilder", new_callable=prompt_builder_mock),
        patch("krita_comfyui.workers.comfy_worker.find_output_node", return_value=None),
        patch("krita_comfyui.workers.comfy_worker.ComfyClient"),
    ):
        worker = ComfyWorker(
            logger=MagicMock(),
            server_url="http://localhost",
            workflow_name="bad_wf",
            prompt_text="foo",
            cfg=mock_cfg,
            seed=None,
            image_prompt=None,
        )

        # Act
        catcher = _run_comfy_worker_and_wait(worker, qapp)

    assert len(catcher.finished) == 0
    assert len(catcher.error) == 1
    assert "No 'SaveImageWebsocket' output node found." in catcher.error[0]


if __name__ == "__main__":
    pytest.main(["-vv", __file__])
